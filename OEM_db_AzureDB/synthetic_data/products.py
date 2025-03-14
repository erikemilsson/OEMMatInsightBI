import datetime
import random
from faker import Faker

fake = Faker()

# --- Helper Functions ---

def generate_realistic_price(price_tier):
    if price_tier == 'budget':
        return round(random.uniform(300, 600), 2)
    elif price_tier == 'mid-range':
        return round(random.uniform(600, 1200), 2)
    elif price_tier == 'premium':
        return round(random.uniform(1200, 2500), 2)
    return 0

def generate_realistic_specs(price_tier):
    if price_tier == 'budget':
        motor_power = random.randint(200, 400)
        battery_capacity = random.randint(200, 400)
        max_speed = random.randint(15, 25)
    elif price_tier == 'mid-range':
        motor_power = random.randint(400, 700)
        battery_capacity = random.randint(400, 600)
        max_speed = random.randint(25, 35)
    elif price_tier == 'premium':
        motor_power = random.randint(700, 1000)
        battery_capacity = random.randint(600, 800)
        max_speed = random.randint(35, 45)
    return motor_power, battery_capacity, max_speed

def generate_realistic_launch_date():
    start_date = datetime.date(2020, 1, 1)
    end_date = datetime.date(2024, 1, 1) # Mostly past dates for launch
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    random_number_of_days = random.randrange(days_between_dates)
    return start_date + datetime.timedelta(days=random_number_of_days)

def generate_future_launch_date():
    start_date = datetime.date(2025, 1, 1)
    end_date = datetime.date(2026, 1, 1)
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    random_number_of_days = random.randrange(days_between_dates)
    return start_date + datetime.timedelta(days=random_number_of_days)

def generate_seasonal_order_date():
    year = random.randint(2023, 2024)
    month = random.choices(
        [i for i in range(1, 13)],
        weights=[5, 5, 7, 8, 9, 12, 12, 12, 10, 8, 7, 5] # Summer months higher weight
    )[0]
    day = random.randint(1, 28) # Keep it simple, no month-end checks
    return datetime.date(year, month, day)

def generate_lead_time_reorder(material_category):
    if material_category in ['Electronics', 'Motors', 'Batteries']:
        lead_time = random.randint(3, 8) # Longer lead times for complex components
        reorder_point = random.randint(50, 200)
    elif material_category in ['Metal', 'Plastic', 'Rubber']:
        lead_time = random.randint(1, 4) # Shorter lead times for raw materials
        reorder_point = random.randint(100, 500)
    elif material_category == 'Consumables':
        lead_time = random.randint(1, 2)
        reorder_point = random.randint(500, 1000)
    else:
        lead_time = random.randint(2, 5)
        reorder_point = random.randint(200, 400)
    return lead_time, reorder_point

def generate_profit_margin(price_tier):
    if price_tier == 'budget':
        return round(random.uniform(0.10, 0.15), 2) # Lower margin
    elif price_tier == 'mid-range':
        return round(random.uniform(0.15, 0.25), 2) # Medium margin
    elif price_tier == 'premium':
        return round(random.uniform(0.20, 0.35), 2) # Higher margin
    return 0.15


# --- Data Generation Functions for Tables ---

def generate_products(num_products=20):
    products_data = []
    price_tiers = ['budget'] * 5 + ['mid-range'] * 10 + ['premium'] * 5

    for i in range(num_products):
        price_tier = price_tiers[i]
        product_name = f"Scooter Model {i+1}"
        model_number = f"SC-{fake.random_number(digits=4)}"
        price = generate_realistic_price(price_tier)
        motor_power, battery_capacity, max_speed = generate_realistic_specs(price_tier)
        description = f"{price_tier.capitalize()} electric scooter with {motor_power}W motor and {battery_capacity}Wh battery."
        launch_date = generate_realistic_launch_date()
        profit_margin = generate_profit_margin(price_tier)

        product = {
            'product_id': i + 1,
            'product_name': product_name,
            'model_number': model_number,
            'description': description,
            'price': price,
            'motor_power_watts': motor_power,
            'battery_capacity_wh': battery_capacity,
            'max_speed_kmh': max_speed,
            'launch_date': launch_date.strftime('%Y-%m-%d'),
            'profit_margin': profit_margin
        }
        products_data.append(product)

    # Introduce Errors
    products_data[0]['max_speed_kmh'] = 85  # Unrealistically high max speed
    products_data[1]['max_speed_kmh'] = 95  # Unrealistically high max speed
    products_data[2]['battery_capacity_wh'] = None # Missing battery capacity
    products_data[3]['launch_date'] = generate_future_launch_date().strftime('%Y-%m-%d') # Future launch date

    return products_data

def generate_material_categories():
    categories = [
        {'category_id': 1, 'category_name': 'Electronics'},
        {'category_id': 2, 'category_name': 'Metal'},
        {'category_id': 3, 'category_name': 'Plastic'},
        {'category_id': 4, 'category_name': 'Rubber'},
        {'category_id': 5, 'category_name': 'Batteries'},
        {'category_id': 6, 'category_name': 'Motors'},
        {'category_id': 7, 'category_name': 'Fasteners'},
        {'category_id': 8, 'category_name': 'Consumables'},
        {'category_id': 9, 'category_name': 'Packaging'},
        {'category_id': 10, 'category_name': 'Other'}
    ]
    return categories

def generate_unit_of_measure():
    units = [
        {'unit_id': 1, 'unit_name': 'Piece'},
        {'unit_id': 2, 'unit_name': 'Kg'},
        {'unit_id': 3, 'unit_name': 'Meter'},
        {'unit_id': 4, 'unit_name': 'Set'},
        {'unit_id': 5, 'unit_name': 'Liter'},
        {'unit_id': 6, 'unit_name': 'Unit'}
    ]
    return units

def generate_materials(num_materials=250):
    materials_data = []
    categories = generate_material_categories()
    units = generate_unit_of_measure()

    material_names = [
        # Electronics
        "Microcontroller", "Motor Controller IC", "Display Unit", "LED Headlight", "LED Taillight", "Wiring Harness", "Connectors", "Throttle Sensor", "Brake Sensor", "GPS Module",
        # Metal
        "Aluminum Frame Tubing", "Steel Steering Column", "Aluminum Handlebar", "Steel Fork", "Aluminum Wheel Rim", "Steel Brake Disc", "Aluminum Kickstand", "Steel Mudguard Bracket",
        # Plastic
        "ABS Plastic Body Panel", "PP Plastic Footrest", "PVC Cable Housing", "Nylon Cable Ties", "Plastic Handlebar Grips", "Plastic Battery Casing", "Plastic Light Housing",
        # Rubber
        "Rubber Tire", "Rubber Inner Tube", "Rubber Brake Lever Grip", "Rubber Foot Pad", "Rubber Cable Grommet",
        # Batteries
        "Lithium-ion Battery Cell", "Battery Management System (BMS)", "Battery Connector", "Battery Wiring", "Battery Thermal Pad",
        # Motors
        "Brushless DC Motor Stator", "Motor Rotor", "Motor Magnet", "Motor Hall Sensor", "Motor Winding Wire", "Motor Bearing",
        # Fasteners
        "M5 Bolt", "M6 Screw", "M4 Nut", "Washer", "Rivet", "Self-Tapping Screw",
        # Consumables
        "Grease", "Threadlocker", "Solder", "Cable Lubricant", "Cleaning Solution",
        # Packaging
        "Cardboard Box", "Foam Insert", "Bubble Wrap", "Packaging Tape", "Styrofoam Protector",
        # Other
        "Paint", "Adhesive", "Label", "Instruction Manual", "Warranty Card"
    ]

    category_weights = [ # Roughly distribute materials across categories
        ('Electronics', 0.2), ('Metal', 0.25), ('Plastic', 0.15), ('Rubber', 0.1),
        ('Batteries', 0.05), ('Motors', 0.05), ('Fasteners', 0.1), ('Consumables', 0.05),
        ('Packaging', 0.03), ('Other', 0.02)
    ]

    used_material_names = set() # Ensure unique material names
    for i in range(num_materials):
        while True: # Ensure unique name
            material_name_candidate = random.choice(material_names)
            if material_name_candidate not in used_material_names:
                material_name = material_name_candidate
                used_material_names.add(material_name)
                break

        category_choice = random.choices([cat[0] for cat in category_weights], weights=[cat[1] for cat in category_weights])[0]
        category_id = next(cat['category_id'] for cat in categories if cat['category_name'] == category_choice)

        if category_choice in ['Kg', 'Metal', 'Plastic', 'Rubber']:
            unit_id = 2 # Kg
        elif category_choice in ['Batteries', 'Motors', 'Electronics', 'Packaging', 'Other']:
            unit_id = 1 # Piece
        elif category_choice == 'Consumables':
            unit_id = random.choice([1, 5]) # Piece or Liter
        elif category_choice == 'Fasteners':
            unit_id = 1 # Piece
        else:
            unit_id = 1 # Default to Piece

        material = {
            'material_id': i + 1,
            'material_name': material_name,
            'material_category_id': category_id,
            'unit_of_measure_id': unit_id
        }
        materials_data.append(material)
    return materials_data

def generate_suppliers(num_suppliers=50):
    suppliers_data = []
    for i in range(num_suppliers):
        supplier_name = fake.company()
        contact_person = fake.name()
        contact_email = fake.email()
        contact_phone = fake.phone_number()
        supplier = {
            'supplier_id': i + 1,
            'supplier_name': supplier_name,
            'contact_person': contact_person,
            'contact_email': contact_email,
            'contact_phone': contact_phone
        }
        suppliers_data.append(supplier)
    return suppliers_data

def generate_bom(products_data):
    bom_data = []
    for product in products_data:
        bom_data.append({'bom_id': product['product_id'], 'product_id': product['product_id'], 'bom_name': f"BOM for {product['product_name']}"})
    return bom_data

def generate_bom_items(bom_data, materials_data, products_data):
    bom_items_data = []
    for bom in bom_data:
        product = next(p for p in products_data if p['product_id'] == bom['product_id'])
        price_tier = ""
        if 300 <= product['price'] <= 600: price_tier = 'budget'
        elif 600 < product['price'] <= 1200: price_tier = 'mid-range'
        else: price_tier = 'premium'

        num_bom_items = random.randint(10, 25) if price_tier != 'budget' else random.randint(8, 15) # More BOM items for higher tier

        used_material_ids = set() # Prevent duplicate materials in one BOM
        for _ in range(num_bom_items):
            while True: # Ensure unique material in BOM and not battery/motor directly
                material = random.choice(materials_data)
                if material['material_id'] not in used_material_ids and 'Battery' not in material['material_name'] and 'Motor' not in material['material_name']: # Avoid listing raw battery cells if possible for BOM complexity
                    material_id = material['material_id']
                    used_material_ids.add(material_id)
                    break

            quantity = random.randint(1, 5) if material['unit_of_measure_id'] == 1 else round(random.uniform(0.1, 2), 2) # Pieces or KGs etc.

            bom_items_data.append({
                'bom_item_id': len(bom_items_data) + 1,
                'bom_id': bom['bom_id'],
                'material_id': material_id,
                'quantity': quantity
            })

        # Add Battery and Motor as BOM items explicitly - ensures each product has them
        battery_material = next((m for m in materials_data if 'Battery' in m['material_name'] and 'Cell' not in m['material_name']), None) # Try to pick a battery pack, not just cells
        if battery_material:
            bom_items_data.append({
                'bom_item_id': len(bom_items_data) + 1,
                'bom_id': bom['bom_id'],
                'material_id': battery_material['material_id'],
                'quantity': 1
            })
        motor_material = next((m for m in materials_data if 'Motor' in m['material_name'] and 'Component' not in m['material_name'] and 'Part' not in m['material_name'] and 'Wire' not in m['material_name']), None) # Try to pick a motor unit
        if motor_material:
             bom_items_data.append({
                'bom_item_id': len(bom_items_data) + 1,
                'bom_id': bom['bom_id'],
                'material_id': motor_material['material_id'],
                'quantity': 1
            })

    return bom_items_data

def generate_inventory(materials_data, suppliers_data):
    inventory_data = []
    for material in materials_data:
        lead_time, reorder_point = generate_lead_time_reorder(next(cat['category_name'] for cat in generate_material_categories() if cat['category_id'] == material['material_category_id']))
        inventory_data.append({
            'inventory_id': material['material_id'], # Inventory ID can be same as material ID for simplicity
            'material_id': material['material_id'],
            'supplier_id': random.choice(suppliers_data)['supplier_id'],
            'quantity_on_hand': random.randint(50, 1000),
            'reorder_point': reorder_point,
            'lead_time_days': lead_time
        })
    return inventory_data

def generate_customers(num_customers=100):
    customers_data = []
    for i in range(num_customers):
        customer_name = fake.name()
        email = fake.email()
        phone_number = fake.phone_number()
        address = fake.address()
        customer = {
            'customer_id': i + 1,
            'customer_name': customer_name,
            'email': email,
            'phone_number': phone_number,
            'address': address
        }
        customers_data.append(customer)
    return customers_data

def generate_order_status():
    status_options = [
        {'status_id': 1, 'status_name': 'Pending'},
        {'status_id': 2, 'status_name': 'Processing'},
        {'status_id': 3, 'status_name': 'Shipped'},
        {'status_id': 4, 'status_name': 'Delivered'},
        {'status_id': 5, 'status_name': 'Cancelled'}
    ]
    return status_options

def generate_sales_orders(customers_data, order_status_options, products_data, num_orders=500):
    sales_orders_data = []
    sales_order_items_data = []
    order_item_id_counter = 1

    for i in range(num_orders):
        order_date = generate_seasonal_order_date()
        customer = random.choice(customers_data)
        status = random.choice(order_status_options)

        sales_order = {
            'order_id': i + 1,
            'customer_id': customer['customer_id'],
            'order_date': order_date.strftime('%Y-%m-%d'),
            'order_status_id': status['status_id']
        }
        sales_orders_data.append(sales_order)

        # Generate 1-3 items per order
        num_items = random.randint(1, 3)
        for _ in range(num_items):
            product = random.choice(products_data)
            quantity = random.randint(1, 5)
            sales_order_item = {
                'order_item_id': order_item_id_counter,
                'order_id': sales_order['order_id'],
                'product_id': product['product_id'],
                'quantity': quantity,
                'unit_price': product['price']
            }
            sales_order_items_data.append(sales_order_item)
            order_item_id_counter += 1

    return sales_orders_data, sales_order_items_data


# --- Generate and Print Data (CSV Format) ---

products_data = generate_products()
material_categories_data = generate_material_categories()
unit_of_measure_data = generate_unit_of_measure()
materials_data = generate_materials()
suppliers_data = generate_suppliers()
bom_data = generate_bom(products_data)
bom_items_data = generate_bom_items(bom_data, materials_data, products_data)
inventory_data = generate_inventory(materials_data, suppliers_data)
customers_data = generate_customers()
order_status_data = generate_order_status()
sales_orders_data, sales_order_items_data = generate_sales_orders(customers_data, order_status_data, products_data)


def print_csv(table_name, data):
    if not data:
        print(f"\n--- {table_name} (No Data) ---")
        return

    print(f"\n--- {table_name} ---")
    columns = data[0].keys()
    print(",".join(columns)) # Header row
    for row_data in data:
        row_values = [str(row_data[col]) if row_data[col] is not None else '' for col in columns] # Handle None values for CSV
        print(",".join(row_values))

print_csv("material_categories", material_categories_data)
print_csv("unit_of_measure", unit_of_measure_data)
print_csv("products", products_data)
print_csv("materials", materials_data)
print_csv("suppliers", suppliers_data)
print_csv("BOM", bom_data)
print_csv("BOM_items", bom_items_data)
print_csv("inventory", inventory_data)
print_csv("customers", customers_data)
print_csv("order_status", order_status_data)
print_csv("sales_orders", sales_orders_data)
print_csv("sales_order_items", sales_order_items_data)