# Table Attribute Descriptions

Products Table, Materials Table, 

## Products Table

- **product_id:** Unique identifier for each product
- **product_code:** Short code/SKU for the product used in operations
- **product_name:** Name of the electric scooter model
- **description:** Detailed description of the product
- **product_type:** Category of product (e.g., commuter, off-road, performance)
- **model_number:** Manufacturer's model number
- **weight_kg:** Weight of the product in kilograms
- **dimensions:** Physical dimensions (length x width x height)
- **max_speed_kmh:** Maximum speed in kilometers per hour
- **battery_capacity_wh:** Battery capacity in watt-hours
- **motor_power_w:** Motor power in watts
- **status:** Current product status (active or discontinued)
- **launch_date:** Date when product was launched
- **msrp:** Manufacturer's suggested retail price
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Materials Table

- **material_id:** Unique identifier for each material
- **material_code:** Short code for the material
- **material_name:** Name of the material
- **description:** Detailed description of the material
- **category_id:** Foreign key to material category
- **uom_id:** Foreign key to unit of measure
- **unit_cost:** Cost per unit of material
- **reorder_point:** Inventory level that triggers reordering
- **lead_time_days:** Days required to receive material after ordering
- **supplier_id:** Primary supplier for this material
- **alternative_supplier_id:** Backup supplier for this material
- **is_raw_material:** Flag indicating if it's a raw material
- **is_purchased:** Flag indicating if material is purchased externally
- **is_manufactured:** Flag indicating if material is manufactured in-house
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Bill of Materials (BOM) Table

- **bom_id:** Unique identifier for each BOM
- **product_id:** Foreign key to the product
- **bom_level:** Hierarchical level in multi-level BOMs
- **version:** Version number of this BOM
- **effective_date:** Date when this BOM becomes effective
- **expiration_date:** Date when this BOM expires
- **approval_status:** Current approval status of the BOM
- **created_by:** User who created the BOM
- **approved_by:** User who approved the BOM
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## BOM Items Table

- **bom_item_id:** Unique identifier for each BOM line item
- **bom_id:** Foreign key to the BOM
- **material_id:** Foreign key to the material used
- **quantity:** Quantity of material required
- **uom_id:** Unit of measure for the quantity
- **position_number:** Order/position in the assembly process
- **notes:** Additional notes about this component
- **is_critical_component:** Flag for components critical to product function
- **scrap_factor:** Expected waste percentage during production
- **substitution_allowed:** Flag indicating if substitutes are acceptable
- **substitute_material_id:** Alternative material that can be used
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Sales Orders Table

- **order_id:** Unique identifier for each sales order
- **order_number:** Human-readable order number
- **customer_id:** Foreign key to the customer
- **order_date:** Date when order was placed
- **required_date:** Date when customer needs the order
- **shipped_date:** Date when order was shipped
- **status_id:** Current status of the order
- **total_amount:** Total monetary amount of the order
- **payment_terms:** Terms of payment for this order
- **shipping_method:** Method used for shipping
- **shipping_cost:** Cost of shipping
- **tax_amount:** Total tax applied to the order
- **discount_amount:** Total discount applied to the order
- **salesperson_id:** Employee who made the sale
- **notes:** Additional notes about the order
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Sales Order Items Table

- **order_item_id:** Unique identifier for each order line item
- **order_id:** Foreign key to the sales order
- **product_id:** Foreign key to the product ordered
- **quantity:** Quantity of product ordered
- **unit_price:** Price per unit at time of order
- **discount_percent:** Discount percentage applied to this line
- **tax_rate:** Tax rate applied to this line
- **line_total:** Total cost for this line item
- **status_id:** Current status of this line item
- **projected_fulfillment_date:** Expected date of fulfillment
- **actual_fulfillment_date:** Actual date of fulfillment
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Material Categories Table

- **category_id:** Unique identifier for each category
- **category_name:** Name of the material category
- **description:** Description of the category
- **parent_category_id:** Parent category for hierarchical categorization
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Units of Measure Table

- **uom_id:** Unique identifier for each unit of measure
- **uom_code:** Short code for the unit
- **uom_name:** Full name of the unit of measure
- **description:** Description of the unit
- **uom_type:** Type of measure (weight, length, quantity, etc.)
- **conversion_factor:** Factor to convert to base unit
- **base_uom_id:** Base unit this converts to
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Suppliers Table

- **supplier_id:** Unique identifier for each supplier
- **supplier_name:** Name of the supplier company
- **contact_name:** Name of primary contact
- **email:** Contact email address
- **phone:** Contact phone number
- **address:** Street address
- **city:** City
- **state_province:** State or province
- **postal_code:** Postal/ZIP code
- **country:** Country
- **payment_terms:** Standard payment terms for this supplier
- **lead_time_days:** Average lead time in days
- **minimum_order_value:** Minimum order value required
- **performance_rating:** Supplier performance rating
- **status:** Active/inactive status
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Inventory Table

- **inventory_id:** Unique identifier for inventory record
- **material_id:** Foreign key to the material
- **warehouse_id:** Location where material is stored
- **location_code:** Specific location within warehouse
- **quantity_on_hand:** Current physical quantity available
- **quantity_allocated:** Quantity reserved for orders
- **quantity_on_order:** Quantity ordered but not received
- **reorder_point:** Inventory level that triggers reordering
- **reorder_quantity:** Standard quantity to order when reordering
- **last_count_date:** Date of last physical inventory count
- **last_received_date:** Date material was last received
- **last_issued_date:** Date material was last issued
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Customers Table

- **customer_id:** Unique identifier for each customer
- **customer_name:** Name of customer company or individual
- **contact_name:** Name of primary contact
- **email:** Contact email address
- **phone:** Contact phone number
- **address:** Street address
- **city:** City
- **state_province:** State or province
- **postal_code:** Postal/ZIP code
- **country:** Country
- **customer_type:** Type of customer (retail, wholesale, etc.)
- **credit_limit:** Maximum allowed credit
- **payment_terms:** Standard payment terms for this customer
- **discount_percent:** Standard discount percentage
- **status:** Active/inactive status
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated

## Order Status Table

- **status_id:** Unique identifier for each status
- **status_name:** Name of the status (e.g., Pending, Processing)
- **description:** Description of what the status means
- **is_active:** Whether status is currently in use
- **display_order:** Order for displaying statuses in UI
- **created_at:** Timestamp when record was created
- **updated_at:** Timestamp when record was last updated