import sqlite3
import uuid
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from geopy.distance import geodesic
import webbrowser
from urllib.parse import urlencode
import re
import json
from tqdm import tqdm
import geocoder  # For getting the user's current location
import csv  # For CSV export
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import sys

#Market PlaceCode Full implimentation

# Function to get the resource path for PyInstaller
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Paths to database files
recipes_db_path = resource_path('recipes.db')
shops_db_path = resource_path('shops.db')

# Database connections
conn_recipes = sqlite3.connect(recipes_db_path)
cursor_recipes = conn_recipes.cursor()

conn_shops = sqlite3.connect(shops_db_path)
cursor_shops = conn_shops.cursor()

# Create tables if they don't exist
# Recipes Database
cursor_recipes.execute('''
CREATE TABLE IF NOT EXISTS Recipes (
    recipe_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_name TEXT NOT NULL UNIQUE
)
''')

cursor_recipes.execute('''
CREATE TABLE IF NOT EXISTS RecipeIngredients (
    recipe_id INTEGER,
    ingredient_name TEXT,
    quantity REAL,
    unit TEXT,
    FOREIGN KEY (recipe_id) REFERENCES Recipes(recipe_id)
)
''')

# Shops Database
cursor_shops.execute('''
CREATE TABLE IF NOT EXISTS Shops (
    shop_id TEXT PRIMARY KEY,
    shop_name TEXT NOT NULL UNIQUE,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL
)
''')

cursor_shops.execute('''
CREATE TABLE IF NOT EXISTS ShopInventory (
    shop_id TEXT,
    ingredient_name TEXT,
    quantity REAL,
    unit TEXT,
    FOREIGN KEY (shop_id) REFERENCES Shops(shop_id)
)
''')

conn_recipes.commit()
conn_shops.commit()


# Functions for database operations

# Recipes Functions
def add_recipe(recipe_name, ingredients):
    try:
        cursor_recipes.execute('INSERT INTO Recipes (recipe_name) VALUES (?)', (recipe_name,))
        recipe_id = cursor_recipes.lastrowid
        for ingredient in ingredients:
            cursor_recipes.execute('''
            INSERT INTO RecipeIngredients (recipe_id, ingredient_name, quantity, unit)
            VALUES (?, ?, ?, ?)
            ''', (recipe_id, ingredient['name'], ingredient['quantity'], ingredient['unit']))
        conn_recipes.commit()
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Recipe '{recipe_name}' already exists.")


def get_all_recipes():
    cursor_recipes.execute('SELECT recipe_id, recipe_name FROM Recipes')
    return cursor_recipes.fetchall()


def update_recipe(recipe_id, new_name, new_ingredients):
    try:
        cursor_recipes.execute('UPDATE Recipes SET recipe_name = ? WHERE recipe_id = ?', (new_name, recipe_id))
        cursor_recipes.execute('DELETE FROM RecipeIngredients WHERE recipe_id = ?', (recipe_id,))
        for ingredient in new_ingredients:
            cursor_recipes.execute('''
            INSERT INTO RecipeIngredients (recipe_id, ingredient_name, quantity, unit)
            VALUES (?, ?, ?, ?)
            ''', (recipe_id, ingredient['name'], ingredient['quantity'], ingredient['unit']))
        conn_recipes.commit()
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Recipe name '{new_name}' already exists.")


def delete_recipe(recipe_id):
    cursor_recipes.execute('DELETE FROM RecipeIngredients WHERE recipe_id = ?', (recipe_id,))
    cursor_recipes.execute('DELETE FROM Recipes WHERE recipe_id = ?', (recipe_id,))
    conn_recipes.commit()


# Shops Functions
def add_shop(shop_name, latitude, longitude, inventory):
    try:
        shop_id = str(uuid.uuid4())
        cursor_shops.execute('''
        INSERT INTO Shops (shop_id, shop_name, latitude, longitude)
        VALUES (?, ?, ?, ?)
        ''', (shop_id, shop_name, latitude, longitude))
        for item in inventory:
            cursor_shops.execute('''
            INSERT INTO ShopInventory (shop_id, ingredient_name, quantity, unit)
            VALUES (?, ?, ?, ?)
            ''', (shop_id, item['name'], item['quantity'], item['unit']))
        conn_shops.commit()
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Shop name '{shop_name}' already exists.")


def get_all_shops():
    cursor_shops.execute('SELECT shop_id, shop_name FROM Shops')
    return cursor_shops.fetchall()


def update_shop(shop_id, new_name, new_latitude, new_longitude, new_inventory):
    try:
        cursor_shops.execute('''
        UPDATE Shops
        SET shop_name = ?, latitude = ?, longitude = ?
        WHERE shop_id = ?
        ''', (new_name, new_latitude, new_longitude, shop_id))
        cursor_shops.execute('DELETE FROM ShopInventory WHERE shop_id = ?', (shop_id,))
        for item in new_inventory:
            cursor_shops.execute('''
            INSERT INTO ShopInventory (shop_id, ingredient_name, quantity, unit)
            VALUES (?, ?, ?, ?)
            ''', (shop_id, item['name'], item['quantity'], item['unit']))
        conn_shops.commit()
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Shop name '{new_name}' already exists.")


def delete_shop(shop_id):
    cursor_shops.execute('DELETE FROM ShopInventory WHERE shop_id = ?', (shop_id,))
    cursor_shops.execute('DELETE FROM Shops WHERE shop_id = ?', (shop_id,))
    conn_shops.commit()


# Geospatial Function
def calculate_distance(coord1, coord2):
    return geodesic(coord1, coord2).kilometers


# Corrected find_nearby_shops_for_recipe Function
def find_nearby_shops_for_recipe(recipe_id, user_location, radius_km):
    """
    Optimized version of finding nearby shops for a recipe using bulk data retrieval.
    """
    try:
        # Step 1: Get required ingredients
        cursor_recipes.execute('''
            SELECT ingredient_name, quantity, unit FROM RecipeIngredients WHERE recipe_id = ?
        ''', (recipe_id,))
        required_ingredients = cursor_recipes.fetchall()

        if not required_ingredients:
            return {'type': 'no_ingredients', 'message': 'No ingredients found for the selected recipe.'}

        # Convert to dictionary for easy access
        ingredients_needed = {name: {'quantity': qty, 'unit': unit} for name, qty, unit in required_ingredients}

        # Step 2: Get all shops
        cursor_shops.execute('SELECT shop_id, shop_name, latitude, longitude FROM Shops')
        all_shops = cursor_shops.fetchall()

        # Step 3: Identify nearby shops
        nearby_shops = []
        shop_ids_within_radius = []
        for shop_id, shop_name, shop_lat, shop_lon in all_shops:
            shop_location = (shop_lat, shop_lon)
            distance = calculate_distance(user_location, shop_location)
            if distance <= radius_km:
                nearby_shops.append({
                    'shop_id': shop_id,
                    'shop_name': shop_name,
                    'latitude': shop_lat,
                    'longitude': shop_lon,
                    'distance': distance
                })
                shop_ids_within_radius.append(shop_id)

        if not nearby_shops:
            return {'type': 'no_shops', 'message': 'No shops found within the specified radius.'}

        # Step 4: Bulk Fetch Shop Inventories
        if not shop_ids_within_radius:
            return {'type': 'no_shops', 'message': 'No shops found within the specified radius.'}

        # Prepare placeholders for SQL IN clause
        placeholders = ','.join(['?'] * len(shop_ids_within_radius))
        query = f'''
            SELECT shop_id, ingredient_name, quantity, unit
            FROM ShopInventory
            WHERE shop_id IN ({placeholders})
        '''
        cursor_shops.execute(query, shop_ids_within_radius)
        shop_inventories = cursor_shops.fetchall()

        # Organize inventories by shop_id
        shop_inventory_map = {}
        for shop_id, ingredient_name, quantity, unit in shop_inventories:
            if shop_id not in shop_inventory_map:
                shop_inventory_map[shop_id] = {}
            shop_inventory_map[shop_id][ingredient_name] = {'quantity': quantity, 'unit': unit}

        # Initialize variables
        selected_shops = []
        ingredient_to_shop = {}

        # Step 5: Check for Single Shop Fulfillment
        single_shops = []
        for shop in nearby_shops:
            inventory = shop_inventory_map.get(shop['shop_id'], {})
            has_all = True
            for ingredient, details in ingredients_needed.items():
                item = inventory.get(ingredient)
                if not item:
                    has_all = False
                    break
                if item['unit'] != details['unit'] or item['quantity'] < details['quantity']:
                    has_all = False
                    break
            if has_all:
                single_shops.append(shop)

        if single_shops:
            # Map all ingredients to this shop
            ingredient_to_shop = {ingredient: single_shops[0] for ingredient in ingredients_needed.keys()}
            selected_shops = single_shops
            result_type = 'single'
        else:
            # Step 6: Find Multiple Shops Fulfillment
            # Assign each ingredient to the closest shop that has it
            for ingredient, details in ingredients_needed.items():
                required_qty = details['quantity']
                required_unit = details['unit']
                # Find shops that have this ingredient in sufficient quantity and correct unit
                shops_with_ingredient = []
                for shop in nearby_shops:
                    inventory = shop_inventory_map.get(shop['shop_id'], {})
                    item = inventory.get(ingredient)
                    if item and item['unit'] == required_unit and item['quantity'] >= required_qty:
                        shops_with_ingredient.append(shop)
                if not shops_with_ingredient:
                    # Ingredient not available in any nearby shop
                    return {
                        'type': 'unavailable',
                        'ingredient': ingredient
                    }
                # Assign the closest shop
                closest_shop = min(shops_with_ingredient, key=lambda x: x['distance'])
                ingredient_to_shop[ingredient] = closest_shop
            # Collect unique shops from the assignments
            selected_shops_dict = {}
            for shop in ingredient_to_shop.values():
                selected_shops_dict[shop['shop_id']] = shop

            selected_shops = list(selected_shops_dict.values())

            # Sort shops by distance for optimized routing
            selected_shops.sort(key=lambda x: x['distance'])
            result_type = 'multiple' if len(selected_shops) > 1 else 'single'

        # Return the result
        return {
            'type': result_type,
            'shops': selected_shops,
            'ingredient_to_shop': ingredient_to_shop,
            'ingredients_needed': ingredients_needed
        }

    except sqlite3.Error as db_error:
        # Log the error or handle it appropriately
        print(f"Database error: {db_error}")
        return {'type': 'error', 'message': 'An error occurred while accessing the database.'}
    except Exception as e:
        # Handle unexpected exceptions
        print(f"Unexpected error: {e}")
        return {'type': 'error', 'message': 'An unexpected error occurred.'}


# Function to generate Google Maps URL with optimized waypoints
def generate_google_maps_url(user_location, shops):
    """
    Generates a Google Maps URL for directions from the user's location
    to the list of shops in an optimized order.
    """
    base_url = "https://www.google.com/maps/dir/?api=1"
    origin = f"{user_location[0]},{user_location[1]}"

    if not shops:
        return base_url

    waypoints = "|".join([f"{shop['latitude']},{shop['longitude']}" for shop in shops])

    params = {
        'origin': origin,
        'travelmode': 'driving',
        'waypoints': f"optimize:true|{waypoints}"
    }

    url = f"{base_url}&{urlencode(params)}"
    return url


# Function to parse ingredient string
def parse_ingredient(ingredient_str):
    pattern = r'(?P<quantity>\d+(\.\d+)?)\s*(?P<unit>\w+)\s+(?:of\s+)?(?P<name>.+)'
    match = re.match(pattern, ingredient_str)
    if match:
        quantity = float(match.group('quantity'))
        unit = match.group('unit')
        name = match.group('name').strip()
        return {'quantity': quantity, 'unit': unit, 'name': name}
    else:
        # Handle cases without units or quantities
        return {'quantity': None, 'unit': None, 'name': ingredient_str.strip()}


def load_dataset(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data['recipes']


def populate_recipes(recipes):
    for recipe in tqdm(recipes, desc="Populating Recipes"):
        recipe_name = recipe['title'].strip()
        ingredients = recipe['ingredients']

        # Add recipe to Recipes table
        try:
            cursor_recipes.execute('INSERT INTO Recipes (recipe_name) VALUES (?)', (recipe_name,))
            recipe_id = cursor_recipes.lastrowid
        except sqlite3.IntegrityError:
            print(f"Recipe '{recipe_name}' already exists. Skipping.")
            continue

        # Parse and add ingredients to RecipeIngredients table
        for ingredient_str in ingredients:
            parsed = parse_ingredient(ingredient_str)
            cursor_recipes.execute('''
                INSERT INTO RecipeIngredients (recipe_id, ingredient_name, quantity, unit)
                VALUES (?, ?, ?, ?)
            ''', (recipe_id, parsed['name'], parsed['quantity'], parsed['unit']))

    conn_recipes.commit()

# Initialize the main window
root = tk.Tk()
root.title("Recipe and Shop Manager")
root.geometry("800x700")

notebook = ttk.Notebook(root)
notebook.pack(expand=True, fill='both')

# Global application state dictionary
app_state = {}

tab_add_recipe = ttk.Frame(notebook)
notebook.add(tab_add_recipe, text='Add Recipe')

# Recipe Name Entry
tk.Label(tab_add_recipe, text="Recipe Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
entry_recipe_name = tk.Entry(tab_add_recipe, width=50)
entry_recipe_name.grid(row=0, column=1, padx=5, pady=5)

# Ingredients Section
tk.Label(tab_add_recipe, text="Ingredients:").grid(row=1, column=0, padx=5, pady=5, sticky='ne')
frame_ingredients = tk.Frame(tab_add_recipe)
frame_ingredients.grid(row=1, column=1, padx=5, pady=5)

# Ingredient Name
tk.Label(frame_ingredients, text="Name").grid(row=0, column=0, padx=2, pady=2)
entry_ing_name = tk.Entry(frame_ingredients, width=20)
entry_ing_name.grid(row=0, column=1, padx=2, pady=2)

# Quantity
tk.Label(frame_ingredients, text="Quantity").grid(row=0, column=2, padx=2, pady=2)
entry_ing_qty = tk.Entry(frame_ingredients, width=10)
entry_ing_qty.grid(row=0, column=3, padx=2, pady=2)

# Unit
tk.Label(frame_ingredients, text="Unit").grid(row=0, column=4, padx=2, pady=2)
entry_ing_unit = tk.Entry(frame_ingredients, width=10)
entry_ing_unit.grid(row=0, column=5, padx=2, pady=2)


# Add Ingredient Button
def add_ingredient():
    name = entry_ing_name.get().strip()
    qty = entry_ing_qty.get().strip()
    unit = entry_ing_unit.get().strip()
    if not name or not qty or not unit:
        messagebox.showerror("Input Error", "Please fill in all ingredient fields.")
        return
    try:
        qty = float(qty)
        if qty <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Input Error", "Please enter a valid positive number for quantity.")
        return
    listbox_ingredients.insert(tk.END, f"{name}: {qty} {unit}")
    entry_ing_name.delete(0, tk.END)
    entry_ing_qty.delete(0, tk.END)
    entry_ing_unit.delete(0, tk.END)


btn_add_ingredient = tk.Button(frame_ingredients, text="Add Ingredient", command=add_ingredient)
btn_add_ingredient.grid(row=0, column=6, padx=5, pady=2)

# Ingredients Listbox
listbox_ingredients = tk.Listbox(tab_add_recipe, width=60, height=10)
listbox_ingredients.grid(row=2, column=1, padx=5, pady=5)


# Remove Ingredient Button
def remove_ingredient():
    selected = listbox_ingredients.curselection()
    if not selected:
        return
    listbox_ingredients.delete(selected[0])


btn_remove_ingredient = tk.Button(tab_add_recipe, text="Remove Selected Ingredient", command=remove_ingredient)
btn_remove_ingredient.grid(row=3, column=1, padx=5, pady=5, sticky='w')


# Add Recipe Button
def gui_add_recipe():
    recipe_name = entry_recipe_name.get().strip()
    if not recipe_name:
        messagebox.showerror("Input Error", "Recipe name cannot be empty.")
        return
    ingredients = []
    for i in range(listbox_ingredients.size()):
        item = listbox_ingredients.get(i)
        try:
            name_part, qty_unit_part = item.split(':', 1)
            qty, unit = qty_unit_part.strip().split(' ', 1)
            ingredients.append({
                'name': name_part.strip(),
                'quantity': float(qty),
                'unit': unit.strip()
            })
        except ValueError:
            messagebox.showerror("Format Error", f"Invalid ingredient format: '{item}'.")
            return
    if not ingredients:
        messagebox.showerror("Input Error", "Please add at least one ingredient.")
        return
    add_recipe(recipe_name, ingredients)
    messagebox.showinfo("Success", f"Recipe '{recipe_name}' added successfully.")
    # Clear inputs
    entry_recipe_name.delete(0, tk.END)
    listbox_ingredients.delete(0, tk.END)
    load_recipes_in_combobox()  # Refresh recipe list in combobox


btn_add_recipe = tk.Button(tab_add_recipe, text="Add Recipe", command=gui_add_recipe)
btn_add_recipe.grid(row=4, column=1, padx=5, pady=10, sticky='e')


# Import Recipe Dataset Button
def import_data():
    file_path = filedialog.askopenfilename(
        title="Select Recipe Dataset",
        filetypes=(("JSON Files", "*.json"), ("All Files", "*.*"))
    )
    if file_path:
        try:
            recipes = load_dataset(file_path)
            populate_recipes(recipes)
            messagebox.showinfo("Import Successful", "Recipes imported successfully!")
            load_recipes_in_combobox()
            load_manage_recipes()
        except Exception as e:
            messagebox.showerror("Import Failed", f"An error occurred during import: {e}")


btn_import_data = tk.Button(tab_add_recipe, text="Import Recipe Dataset", command=import_data)
btn_import_data.grid(row=5, column=1, padx=5, pady=10, sticky='e')


tab_add_shop = ttk.Frame(notebook)
notebook.add(tab_add_shop, text='Add Shop')

# Shop Name Entry
tk.Label(tab_add_shop, text="Shop Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
entry_shop_name = tk.Entry(tab_add_shop, width=50)
entry_shop_name.grid(row=0, column=1, padx=5, pady=5)

# Latitude Entry
tk.Label(tab_add_shop, text="Latitude:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
entry_latitude = tk.Entry(tab_add_shop, width=50)
entry_latitude.grid(row=1, column=1, padx=5, pady=5)

# Longitude Entry
tk.Label(tab_add_shop, text="Longitude:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
entry_longitude = tk.Entry(tab_add_shop, width=50)
entry_longitude.grid(row=2, column=1, padx=5, pady=5)

# Inventory Section
tk.Label(tab_add_shop, text="Inventory:").grid(row=3, column=0, padx=5, pady=5, sticky='ne')
frame_inventory = tk.Frame(tab_add_shop)
frame_inventory.grid(row=3, column=1, padx=5, pady=5)

# Inventory Name
tk.Label(frame_inventory, text="Name").grid(row=0, column=0, padx=2, pady=2)
entry_inv_name = tk.Entry(frame_inventory, width=20)
entry_inv_name.grid(row=0, column=1, padx=2, pady=2)

# Quantity
tk.Label(frame_inventory, text="Quantity").grid(row=0, column=2, padx=2, pady=2)
entry_inv_qty = tk.Entry(frame_inventory, width=10)
entry_inv_qty.grid(row=0, column=3, padx=2, pady=2)

# Unit
tk.Label(frame_inventory, text="Unit").grid(row=0, column=4, padx=2, pady=2)
entry_inv_unit = tk.Entry(frame_inventory, width=10)
entry_inv_unit.grid(row=0, column=5, padx=2, pady=2)


# Add Inventory Item Button
def add_inventory_item():
    name = entry_inv_name.get().strip()
    qty = entry_inv_qty.get().strip()
    unit = entry_inv_unit.get().strip()
    if not name or not qty or not unit:
        messagebox.showerror("Input Error", "Please fill in all inventory fields.")
        return
    try:
        qty = float(qty)
        if qty <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Input Error", "Please enter a valid positive number for quantity.")
        return
    listbox_inventory.insert(tk.END, f"{name}: {qty} {unit}")
    entry_inv_name.delete(0, tk.END)
    entry_inv_qty.delete(0, tk.END)
    entry_inv_unit.delete(0, tk.END)


btn_add_inventory = tk.Button(frame_inventory, text="Add Item", command=add_inventory_item)
btn_add_inventory.grid(row=0, column=6, padx=5, pady=2)

# Inventory Listbox
listbox_inventory = tk.Listbox(tab_add_shop, width=60, height=10)
listbox_inventory.grid(row=4, column=1, padx=5, pady=5)


# Remove Inventory Item Button
def remove_inventory_item():
    selected = listbox_inventory.curselection()
    if not selected:
        return
    listbox_inventory.delete(selected[0])


btn_remove_inventory = tk.Button(tab_add_shop, text="Remove Selected Inventory", command=remove_inventory_item)
btn_remove_inventory.grid(row=5, column=1, padx=5, pady=5, sticky='w')


# Add Shop Button
def gui_add_shop():
    shop_name = entry_shop_name.get().strip()
    if not shop_name:
        messagebox.showerror("Input Error", "Shop name cannot be empty.")
        return
    try:
        latitude = float(entry_latitude.get())
        longitude = float(entry_longitude.get())
    except ValueError:
        messagebox.showerror("Input Error", "Please enter valid numerical values for latitude and longitude.")
        return
    inventory = []
    for i in range(listbox_inventory.size()):
        item = listbox_inventory.get(i)
        try:
            name_part, qty_unit_part = item.split(':', 1)
            qty, unit = qty_unit_part.strip().split(' ', 1)
            inventory.append({
                'name': name_part.strip(),
                'quantity': float(qty),
                'unit': unit.strip()
            })
        except ValueError:
            messagebox.showerror("Format Error", f"Invalid inventory format: '{item}'.")
            return
    if not inventory:
        messagebox.showerror("Input Error", "Please add at least one inventory item.")
        return
    add_shop(shop_name, latitude, longitude, inventory)
    messagebox.showinfo("Success", f"Shop '{shop_name}' added successfully.")
    # Clear inputs
    entry_shop_name.delete(0, tk.END)
    entry_latitude.delete(0, tk.END)
    entry_longitude.delete(0, tk.END)
    listbox_inventory.delete(0, tk.END)
    load_shops_in_manage_shops()  # Refresh shops list in manage shops tab


btn_add_shop = tk.Button(tab_add_shop, text="Add Shop", command=gui_add_shop)
btn_add_shop.grid(row=6, column=1, padx=5, pady=10, sticky='e')


tab_find_shops = ttk.Frame(notebook)
notebook.add(tab_find_shops, text='Find Nearby Shops')

# User Location Entries
tk.Label(tab_find_shops, text="Your Latitude:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
entry_user_latitude = tk.Entry(tab_find_shops, width=50)
entry_user_latitude.grid(row=0, column=1, padx=5, pady=5)

tk.Label(tab_find_shops, text="Your Longitude:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
entry_user_longitude = tk.Entry(tab_find_shops, width=50)
entry_user_longitude.grid(row=1, column=1, padx=5, pady=5)

# Add the "Use Current Location" button
def get_current_location():
    try:
        # Use geocoder to get the user's location based on IP
        g = geocoder.ip('me')
        if g.ok:
            lat, lon = g.latlng
            # Fill the latitude and longitude entries
            entry_user_latitude.delete(0, tk.END)
            entry_user_latitude.insert(0, str(lat))
            entry_user_longitude.delete(0, tk.END)
            entry_user_longitude.insert(0, str(lon))
            messagebox.showinfo("Location Retrieved", "Your current location has been filled in.")
        else:
            messagebox.showerror("Error", "Could not retrieve your location.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while retrieving your location: {e}")

btn_use_current_location = tk.Button(tab_find_shops, text="Use Current Location", command=get_current_location)
btn_use_current_location.grid(row=2, column=1, padx=5, pady=5, sticky='w')

# Recipe Selection with Combobox
tk.Label(tab_find_shops, text="Select Recipe:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
combo_recipes = ttk.Combobox(tab_find_shops, width=47, state='readonly')
combo_recipes.grid(row=3, column=1, padx=5, pady=5)
refresh_recipes = True  # Flag to refresh recipes list


def load_recipes_in_combobox():
    recipes = get_all_recipes()
    recipe_names = [f"{rid}: {rname}" for rid, rname in recipes]
    combo_recipes['values'] = recipe_names


load_recipes_in_combobox()

# Radius Entry
tk.Label(tab_find_shops, text="Search Radius (km):").grid(row=4, column=0, padx=5, pady=5, sticky='e')
entry_radius = tk.Entry(tab_find_shops, width=50)
entry_radius.grid(row=4, column=1, padx=5, pady=5)
entry_radius.insert(0, "10")  # Default radius

# Find Shops Button
def gui_find_shops():
    try:
        user_lat = float(entry_user_latitude.get())
        user_lon = float(entry_user_longitude.get())
        radius = float(entry_radius.get())
    except ValueError:
        messagebox.showerror("Input Error", "Please enter valid numerical values for location and radius.")
        return
    selected_recipe = combo_recipes.get()
    if not selected_recipe:
        messagebox.showerror("Input Error", "Please select a recipe.")
        return
    try:
        recipe_id = int(selected_recipe.split(':')[0])
    except ValueError:
        messagebox.showerror("Format Error", "Invalid recipe selection.")
        return
    result = find_nearby_shops_for_recipe(recipe_id, (user_lat, user_lon), radius)
    listbox_results.delete(0, tk.END)

    if result['type'] == 'single':
        listbox_results.insert(tk.END, "Single shop that has all ingredients:")
        for shop in result['shops']:
            shop_name = shop['shop_name']
            listbox_results.insert(tk.END, f"Shop Name: {shop_name}, Distance: {shop['distance']:.2f} km")
        # Display ingredients to buy
        listbox_results.insert(tk.END, "\nIngredients to buy:")
        for ingredient, shop in result['ingredient_to_shop'].items():
            listbox_results.insert(tk.END, f"{ingredient}: Buy from {shop['shop_name']}")
        # Enable View Route and Export buttons
        btn_view_route.config(state='normal')
        btn_export_list.config(state='normal')
        # Store selected shops and ingredient mapping in app_state
        app_state['selected_shops'] = result['shops']
        app_state['ingredient_to_shop'] = result['ingredient_to_shop']
        app_state['ingredients_needed'] = result['ingredients_needed']
    elif result['type'] == 'multiple':
        listbox_results.insert(tk.END, "Multiple shops required to cover all ingredients:")
        for shop in result['shops']:
            shop_name = shop['shop_name']
            listbox_results.insert(tk.END, f"Shop Name: {shop_name}, Distance: {shop['distance']:.2f} km")
        # Display ingredients to buy from each shop
        listbox_results.insert(tk.END, "\nIngredients to buy from each shop:")
        # Create a mapping from shop_id to list of ingredients
        shop_to_ingredients = {}
        for ingredient, shop in result['ingredient_to_shop'].items():
            shop_id = shop['shop_id']
            if shop_id not in shop_to_ingredients:
                shop_to_ingredients[shop_id] = []
            shop_to_ingredients[shop_id].append(ingredient)
        for shop in result['shops']:
            shop_name = shop['shop_name']
            ingredients = shop_to_ingredients.get(shop['shop_id'], [])
            listbox_results.insert(tk.END, f"\nShop: {shop_name}")
            for ingredient in ingredients:
                listbox_results.insert(tk.END, f"  - {ingredient}")
        # Enable View Route and Export buttons
        btn_view_route.config(state='normal')
        btn_export_list.config(state='normal')
        # Store selected shops and ingredient mapping in app_state
        app_state['selected_shops'] = result['shops']
        app_state['ingredient_to_shop'] = result['ingredient_to_shop']
        app_state['ingredients_needed'] = result['ingredients_needed']
    elif result['type'] == 'unavailable':
        messagebox.showwarning("Unavailable Ingredient",
                               f"Ingredient '{result['ingredient']}' is not available in any nearby shop.")
        btn_view_route.config(state='disabled')
        btn_export_list.config(state='disabled')
    else:
        messagebox.showinfo("No Shops Found", "No shops found within the specified radius.")
        btn_view_route.config(state='disabled')
        btn_export_list.config(state='disabled')


btn_find_shops = tk.Button(tab_find_shops, text="Find Shops", command=gui_find_shops)
btn_find_shops.grid(row=5, column=1, padx=5, pady=5, sticky='e')

# Results Listbox
listbox_results = tk.Listbox(tab_find_shops, width=80, height=15)
listbox_results.grid(row=6, column=0, columnspan=2, padx=5, pady=5)

# View Route Button
def gui_view_route():
    if 'selected_shops' not in app_state:
        messagebox.showwarning("No Shops Selected", "No shops selected to view the route.")
        return
    try:
        user_lat = float(entry_user_latitude.get())
        user_lon = float(entry_user_longitude.get())
        user_location = (user_lat, user_lon)
    except ValueError:
        messagebox.showerror("Input Error", "Invalid user location coordinates.")
        return
    shops = app_state['selected_shops']
    url = generate_google_maps_url(user_location, shops)
    webbrowser.open(url)

btn_view_route = tk.Button(tab_find_shops, text="View Optimized Route on Google Maps", command=gui_view_route,
                           state='disabled')
btn_view_route.grid(row=7, column=1, padx=5, pady=5, sticky='e')

# Export Shopping List Button
def export_shopping_list():
    if 'ingredient_to_shop' not in app_state or 'ingredients_needed' not in app_state:
        messagebox.showerror("No Data", "No shopping list available to export.")
        return

    # Ask user for the export format
    def save_as_csv():
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, mode='w', newline='') as csvfile:
                    fieldnames = ['Ingredient', 'Quantity', 'Unit', 'Shop Name']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for ingredient, shop in app_state['ingredient_to_shop'].items():
                        # Fetch quantity and unit from ingredients_needed
                        details = app_state['ingredients_needed'][ingredient]
                        writer.writerow({
                            'Ingredient': ingredient,
                            'Quantity': details['quantity'],
                            'Unit': details['unit'],
                            'Shop Name': shop['shop_name']
                        })
                messagebox.showinfo("Export Successful", f"Shopping list exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"An error occurred: {e}")

    def save_as_pdf():
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if file_path:
            try:
                c = canvas.Canvas(file_path, pagesize=letter)
                width, height = letter
                c.setFont("Helvetica", 12)
                y = height - 50
                c.drawString(50, y, "Shopping List")
                y -= 30
                for ingredient, shop in app_state['ingredient_to_shop'].items():
                    details = app_state['ingredients_needed'][ingredient]
                    line = f"{ingredient}: {details['quantity']} {details['unit']} - Buy from {shop['shop_name']}"
                    c.drawString(50, y, line)
                    y -= 20
                    if y < 50:
                        c.showPage()
                        y = height - 50
                c.save()
                messagebox.showinfo("Export Successful", f"Shopping list exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"An error occurred: {e}")

    # Create a popup window for export options
    export_window = tk.Toplevel(root)
    export_window.title("Export Shopping List")
    export_window.geometry("300x150")
    tk.Label(export_window, text="Choose Export Format:").pack(pady=10)
    btn_csv = tk.Button(export_window, text="Export as CSV", command=lambda: [save_as_csv(), export_window.destroy()])
    btn_csv.pack(pady=5)
    btn_pdf = tk.Button(export_window, text="Export as PDF", command=lambda: [save_as_pdf(), export_window.destroy()])
    btn_pdf.pack(pady=5)

    # Bring the popup to the front
    export_window.transient(root)
    export_window.grab_set()
    root.wait_window(export_window)


btn_export_list = tk.Button(tab_find_shops, text="Export Shopping List", command=export_shopping_list, state='disabled')
btn_export_list.grid(row=7, column=0, padx=5, pady=5, sticky='w')


def gui_whats_in_season():
    try:
        user_lat = float(entry_user_latitude.get())
        user_lon = float(entry_user_longitude.get())
        radius = float(entry_radius.get())
    except ValueError:
        messagebox.showerror("Input Error", "Please enter valid numerical values for location and radius.")
        return

    user_location = (user_lat, user_lon)

    # Get all recipes
    cursor_recipes.execute('SELECT recipe_id, recipe_name FROM Recipes')
    all_recipes = cursor_recipes.fetchall()

    if not all_recipes:
        messagebox.showinfo("No Recipes", "No recipes found in the database.")
        return

    # Step 2: Get all shops
    cursor_shops.execute('SELECT shop_id, shop_name, latitude, longitude FROM Shops')
    all_shops = cursor_shops.fetchall()

    # Step 3: Identify nearby shops
    nearby_shops = []
    shop_ids_within_radius = []
    for shop_id, shop_name, shop_lat, shop_lon in all_shops:
        shop_location = (shop_lat, shop_lon)
        distance = calculate_distance(user_location, shop_location)
        if distance <= radius:
            nearby_shops.append({
                'shop_id': shop_id,
                'shop_name': shop_name,
                'latitude': shop_lat,
                'longitude': shop_lon,
                'distance': distance
            })
            shop_ids_within_radius.append(shop_id)

    if not nearby_shops:
        messagebox.showinfo("No Shops Found", "No shops found within the specified radius.")
        return

    # Step 4: Bulk Fetch Shop Inventories
    # Prepare placeholders for SQL IN clause
    placeholders = ','.join(['?'] * len(shop_ids_within_radius))
    query = f'''
        SELECT ingredient_name FROM ShopInventory
        WHERE shop_id IN ({placeholders})
        GROUP BY ingredient_name
    '''
    cursor_shops.execute(query, shop_ids_within_radius)
    available_ingredients = set(row[0] for row in cursor_shops.fetchall())

    # Step 5: For each recipe, check if all ingredients are available
    in_season_recipes = []
    for recipe_id, recipe_name in all_recipes:
        cursor_recipes.execute('SELECT ingredient_name FROM RecipeIngredients WHERE recipe_id = ?', (recipe_id,))
        recipe_ingredients = set(row[0] for row in cursor_recipes.fetchall())
        if recipe_ingredients.issubset(available_ingredients):
            in_season_recipes.append(recipe_name)

    # Display the results
    listbox_results.delete(0, tk.END)
    if in_season_recipes:
        listbox_results.insert(tk.END, "Recipes 'In Season' (All ingredients available nearby):")
        for recipe_name in in_season_recipes:
            listbox_results.insert(tk.END, f"- {recipe_name}")
    else:
        listbox_results.insert(tk.END, "No recipes are 'In Season' based on the available ingredients nearby.")

# Add the 'What's in Season' Button
btn_whats_in_season = tk.Button(tab_find_shops, text="What's in Season", command=gui_whats_in_season)
btn_whats_in_season.grid(row=5, column=1, padx=5, pady=5, sticky='w')


tab_manage_recipes = ttk.Frame(notebook)
notebook.add(tab_manage_recipes, text='Manage Recipes')

# Recipe Listbox
listbox_manage_recipes = tk.Listbox(tab_manage_recipes, width=60, height=20)
listbox_manage_recipes.grid(row=0, column=0, rowspan=6, padx=5, pady=5)

def load_manage_recipes():
    listbox_manage_recipes.delete(0, tk.END)
    recipes = get_all_recipes()
    for rid, rname in recipes:
        listbox_manage_recipes.insert(tk.END, f"{rid}: {rname}")

load_manage_recipes()

# Refresh Button for Manage Recipes
def refresh_recipes():
    load_manage_recipes()
    messagebox.showinfo("Refreshed", "Recipe list has been refreshed.")

btn_refresh_recipes = tk.Button(tab_manage_recipes, text="Refresh List", command=refresh_recipes)
btn_refresh_recipes.grid(row=2, column=1, padx=5, pady=5)

# View/Edit Recipe
def view_edit_recipe():
    selected = listbox_manage_recipes.curselection()
    if not selected:
        messagebox.showwarning("No Selection", "Please select a recipe to view/edit.")
        return
    recipe_str = listbox_manage_recipes.get(selected[0])
    recipe_id = int(recipe_str.split(':')[0])

    # Fetch recipe details
    cursor_recipes.execute('SELECT recipe_name FROM Recipes WHERE recipe_id = ?', (recipe_id,))
    recipe_name = cursor_recipes.fetchone()[0]

    cursor_recipes.execute('''
    SELECT ingredient_name, quantity, unit FROM RecipeIngredients WHERE recipe_id = ?
    ''', (recipe_id,))
    ingredients = cursor_recipes.fetchall()

    # Create a new window for editing
    edit_window = tk.Toplevel(root)
    edit_window.title(f"Edit Recipe - {recipe_name}")
    edit_window.geometry("600x400")

    # Recipe Name Entry
    tk.Label(edit_window, text="Recipe Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
    entry_edit_recipe_name = tk.Entry(edit_window, width=40)
    entry_edit_recipe_name.grid(row=0, column=1, padx=5, pady=5)
    entry_edit_recipe_name.insert(0, recipe_name)

    # Ingredients Listbox
    listbox_edit_ingredients = tk.Listbox(edit_window, width=50, height=15)
    listbox_edit_ingredients.grid(row=1, column=1, padx=5, pady=5)

    for ing_name, qty, unit in ingredients:
        listbox_edit_ingredients.insert(tk.END, f"{ing_name}: {qty} {unit}")

    # Ingredient Entry Fields
    frame_edit_ingredients = tk.Frame(edit_window)
    frame_edit_ingredients.grid(row=2, column=1, padx=5, pady=5)

    tk.Label(frame_edit_ingredients, text="Name").grid(row=0, column=0, padx=2, pady=2)
    entry_edit_ing_name = tk.Entry(frame_edit_ingredients, width=20)
    entry_edit_ing_name.grid(row=0, column=1, padx=2, pady=2)

    tk.Label(frame_edit_ingredients, text="Quantity").grid(row=0, column=2, padx=2, pady=2)
    entry_edit_ing_qty = tk.Entry(frame_edit_ingredients, width=10)
    entry_edit_ing_qty.grid(row=0, column=3, padx=2, pady=2)

    tk.Label(frame_edit_ingredients, text="Unit").grid(row=0, column=4, padx=2, pady=2)
    entry_edit_ing_unit = tk.Entry(frame_edit_ingredients, width=10)
    entry_edit_ing_unit.grid(row=0, column=5, padx=2, pady=2)

    # Add Ingredient Button
    def add_edit_ingredient():
        name = entry_edit_ing_name.get().strip()
        qty = entry_edit_ing_qty.get().strip()
        unit = entry_edit_ing_unit.get().strip()
        if not name or not qty or not unit:
            messagebox.showerror("Input Error", "Please fill in all ingredient fields.")
            return
        try:
            qty = float(qty)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid positive number for quantity.")
            return
        listbox_edit_ingredients.insert(tk.END, f"{name}: {qty} {unit}")
        entry_edit_ing_name.delete(0, tk.END)
        entry_edit_ing_qty.delete(0, tk.END)
        entry_edit_ing_unit.delete(0, tk.END)

    btn_add_edit_ingredient = tk.Button(frame_edit_ingredients, text="Add Ingredient", command=add_edit_ingredient)
    btn_add_edit_ingredient.grid(row=0, column=6, padx=5, pady=2)

    # Remove Ingredient Button
    def remove_edit_ingredient():
        selected = listbox_edit_ingredients.curselection()
        if not selected:
            return
        listbox_edit_ingredients.delete(selected[0])

    btn_remove_edit_ingredient = tk.Button(edit_window, text="Remove Selected Ingredient", command=remove_edit_ingredient)
    btn_remove_edit_ingredient.grid(row=3, column=1, padx=5, pady=5, sticky='w')

    # Save Changes Button
    def save_recipe_changes():
        new_name = entry_edit_recipe_name.get().strip()
        if not new_name:
            messagebox.showerror("Input Error", "Recipe name cannot be empty.")
            return
        new_ingredients = []
        for i in range(listbox_edit_ingredients.size()):
            item = listbox_edit_ingredients.get(i)
            try:
                name_part, qty_unit_part = item.split(':', 1)
                qty, unit = qty_unit_part.strip().split(' ', 1)
                new_ingredients.append({
                    'name': name_part.strip(),
                    'quantity': float(qty),
                    'unit': unit.strip()
                })
            except ValueError:
                messagebox.showerror("Format Error", f"Invalid ingredient format: '{item}'.")
                return
        if not new_ingredients:
            messagebox.showerror("Input Error", "Please add at least one ingredient.")
            return
        update_recipe(recipe_id, new_name, new_ingredients)
        messagebox.showinfo("Success", f"Recipe '{new_name}' updated successfully.")
        edit_window.destroy()
        load_manage_recipes()
        load_recipes_in_combobox()

    btn_save_changes = tk.Button(edit_window, text="Save Changes", command=save_recipe_changes)
    btn_save_changes.grid(row=4, column=1, padx=5, pady=10, sticky='e')

# View/Edit Button
btn_view_edit_recipe = tk.Button(tab_manage_recipes, text="View/Edit Recipe", command=view_edit_recipe)
btn_view_edit_recipe.grid(row=0, column=1, padx=5, pady=5)

# Delete Recipe
def delete_selected_recipe():
    selected = listbox_manage_recipes.curselection()
    if not selected:
        messagebox.showwarning("No Selection", "Please select a recipe to delete.")
        return
    recipe_str = listbox_manage_recipes.get(selected[0])
    recipe_id = int(recipe_str.split(':')[0])
    confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this recipe?")
    if confirm:
        delete_recipe(recipe_id)
        messagebox.showinfo("Deleted", "Recipe deleted successfully.")
        load_manage_recipes()
        load_recipes_in_combobox()

btn_delete_recipe = tk.Button(tab_manage_recipes, text="Delete Recipe", command=delete_selected_recipe)
btn_delete_recipe.grid(row=1, column=1, padx=5, pady=5)


tab_manage_shops = ttk.Frame(notebook)
notebook.add(tab_manage_shops, text='Manage Shops')

# Shop Listbox
listbox_manage_shops = tk.Listbox(tab_manage_shops, width=60, height=20)
listbox_manage_shops.grid(row=0, column=0, rowspan=6, padx=5, pady=5)

def load_shops_in_manage_shops():
    listbox_manage_shops.delete(0, tk.END)
    shops = get_all_shops()
    for shop_id, shop_name in shops:
        listbox_manage_shops.insert(tk.END, f"{shop_id}: {shop_name}")

load_shops_in_manage_shops()

# Refresh Button for Manage Shops
def refresh_shops():
    load_shops_in_manage_shops()
    messagebox.showinfo("Refreshed", "Shop list has been refreshed.")

btn_refresh_shops = tk.Button(tab_manage_shops, text="Refresh List", command=refresh_shops)
btn_refresh_shops.grid(row=2, column=1, padx=5, pady=5)

# View/Edit Shop
def view_edit_shop():
    selected = listbox_manage_shops.curselection()
    if not selected:
        messagebox.showwarning("No Selection", "Please select a shop to view/edit.")
        return
    shop_str = listbox_manage_shops.get(selected[0])
    shop_id = shop_str.split(':')[0]

    # Fetch shop details
    cursor_shops.execute('SELECT shop_name, latitude, longitude FROM Shops WHERE shop_id = ?', (shop_id,))
    shop_name, latitude, longitude = cursor_shops.fetchone()

    cursor_shops.execute('''
    SELECT ingredient_name, quantity, unit FROM ShopInventory WHERE shop_id = ?
    ''', (shop_id,))
    inventory = cursor_shops.fetchall()

    # Create a new window for editing
    edit_window = tk.Toplevel(root)
    edit_window.title(f"Edit Shop - {shop_name}")
    edit_window.geometry("600x400")

    # Shop Name Entry
    tk.Label(edit_window, text="Shop Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
    entry_edit_shop_name = tk.Entry(edit_window, width=40)
    entry_edit_shop_name.grid(row=0, column=1, padx=5, pady=5)
    entry_edit_shop_name.insert(0, shop_name)

    # Latitude and Longitude
    tk.Label(edit_window, text="Latitude:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
    entry_edit_latitude = tk.Entry(edit_window, width=40)
    entry_edit_latitude.grid(row=1, column=1, padx=5, pady=5)
    entry_edit_latitude.insert(0, str(latitude))

    tk.Label(edit_window, text="Longitude:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
    entry_edit_longitude = tk.Entry(edit_window, width=40)
    entry_edit_longitude.grid(row=2, column=1, padx=5, pady=5)
    entry_edit_longitude.insert(0, str(longitude))

    # Inventory Listbox
    listbox_edit_inventory = tk.Listbox(edit_window, width=50, height=10)
    listbox_edit_inventory.grid(row=3, column=1, padx=5, pady=5)

    for ing_name, qty, unit in inventory:
        listbox_edit_inventory.insert(tk.END, f"{ing_name}: {qty} {unit}")

    # Inventory Entry Fields
    frame_edit_inventory = tk.Frame(edit_window)
    frame_edit_inventory.grid(row=4, column=1, padx=5, pady=5)

    tk.Label(frame_edit_inventory, text="Name").grid(row=0, column=0, padx=2, pady=2)
    entry_edit_inv_name = tk.Entry(frame_edit_inventory, width=20)
    entry_edit_inv_name.grid(row=0, column=1, padx=2, pady=2)

    tk.Label(frame_edit_inventory, text="Quantity").grid(row=0, column=2, padx=2, pady=2)
    entry_edit_inv_qty = tk.Entry(frame_edit_inventory, width=10)
    entry_edit_inv_qty.grid(row=0, column=3, padx=2, pady=2)

    tk.Label(frame_edit_inventory, text="Unit").grid(row=0, column=4, padx=2, pady=2)
    entry_edit_inv_unit = tk.Entry(frame_edit_inventory, width=10)
    entry_edit_inv_unit.grid(row=0, column=5, padx=2, pady=2)

    # Add Inventory Item Button
    def add_edit_inventory_item():
        name = entry_edit_inv_name.get().strip()
        qty = entry_edit_inv_qty.get().strip()
        unit = entry_edit_inv_unit.get().strip()
        if not name or not qty or not unit:
            messagebox.showerror("Input Error", "Please fill in all inventory fields.")
            return
        try:
            qty = float(qty)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid positive number for quantity.")
            return
        listbox_edit_inventory.insert(tk.END, f"{name}: {qty} {unit}")
        entry_edit_inv_name.delete(0, tk.END)
        entry_edit_inv_qty.delete(0, tk.END)
        entry_edit_inv_unit.delete(0, tk.END)

    btn_add_edit_inventory = tk.Button(frame_edit_inventory, text="Add Item", command=add_edit_inventory_item)
    btn_add_edit_inventory.grid(row=0, column=6, padx=5, pady=2)

    # Remove Inventory Item Button
    def remove_edit_inventory_item():
        selected = listbox_edit_inventory.curselection()
        if not selected:
            return
        listbox_edit_inventory.delete(selected[0])

    btn_remove_edit_inventory = tk.Button(edit_window, text="Remove Selected Inventory", command=remove_edit_inventory_item)
    btn_remove_edit_inventory.grid(row=5, column=1, padx=5, pady=5, sticky='w')

    # Save Changes Button
    def save_shop_changes():
        new_name = entry_edit_shop_name.get().strip()
        if not new_name:
            messagebox.showerror("Input Error", "Shop name cannot be empty.")
            return
        try:
            new_latitude = float(entry_edit_latitude.get())
            new_longitude = float(entry_edit_longitude.get())
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid numerical values for latitude and longitude.")
            return
        new_inventory = []
        for i in range(listbox_edit_inventory.size()):
            item = listbox_edit_inventory.get(i)
            try:
                name_part, qty_unit_part = item.split(':', 1)
                qty, unit = qty_unit_part.strip().split(' ', 1)
                new_inventory.append({
                    'name': name_part.strip(),
                    'quantity': float(qty),
                    'unit': unit.strip()
                })
            except ValueError:
                messagebox.showerror("Format Error", f"Invalid inventory format: '{item}'.")
                return
        if not new_inventory:
            messagebox.showerror("Input Error", "Please add at least one inventory item.")
            return
        update_shop(shop_id, new_name, new_latitude, new_longitude, new_inventory)
        messagebox.showinfo("Success", f"Shop '{new_name}' updated successfully.")
        edit_window.destroy()
        load_shops_in_manage_shops()

    btn_save_shop_changes = tk.Button(edit_window, text="Save Changes", command=save_shop_changes)
    btn_save_shop_changes.grid(row=6, column=1, padx=5, pady=10, sticky='e')

# View/Edit Button
btn_view_edit_shop = tk.Button(tab_manage_shops, text="View/Edit Shop", command=view_edit_shop)
btn_view_edit_shop.grid(row=0, column=1, padx=5, pady=5)

# Delete Shop
def delete_selected_shop():
    selected = listbox_manage_shops.curselection()
    if not selected:
        messagebox.showwarning("No Selection", "Please select a shop to delete.")
        return
    shop_str = listbox_manage_shops.get(selected[0])
    shop_id = shop_str.split(':')[0]
    confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this shop?")
    if confirm:
        delete_shop(shop_id)
        messagebox.showinfo("Deleted", "Shop deleted successfully.")
        load_shops_in_manage_shops()

btn_delete_shop = tk.Button(tab_manage_shops, text="Delete Shop", command=delete_selected_shop)
btn_delete_shop.grid(row=1, column=1, padx=5, pady=5)


root.mainloop()

# Close database connections when the GUI is closed
conn_recipes.close()
conn_shops.close()
