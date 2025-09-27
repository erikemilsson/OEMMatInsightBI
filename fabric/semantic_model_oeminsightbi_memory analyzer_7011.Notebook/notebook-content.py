# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "jupyter",
# META     "jupyter_kernel_name": "python3.11"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "488fb9f8-e635-4683-90c4-ba4fee9dfadb",
# META       "default_lakehouse_name": "oem_lh",
# META       "default_lakehouse_workspace_id": "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9",
# META       "known_lakehouses": [
# META         {
# META           "id": "488fb9f8-e635-4683-90c4-ba4fee9dfadb"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# ## Memory Analyzer
# 
# When you run this notebook, the [Memory Analyzer](https://learn.microsoft.com/python/api/semantic-link-sempy/sempy.fabric?view=semantic-link-python#sempy-fabric-model-memory-analyzer) will show you memory/storage statistics about the objects in your semantic model (i.e. Tables, Columns, Hierarchies, Partitions, and Relationships). These statistics may be used to identify areas of performance optimization and memory reduction for your semantic model.
# 
# ### Powering this feature: Semantic Link
# This notebook leverages [Semantic Link](https://learn.microsoft.com/fabric/data-science/semantic-link-overview), a python library which lets you optimize Fabric items for performance, memory and cost. The "[model_memory_analyzer](https://learn.microsoft.com/python/api/semantic-link-sempy/sempy.fabric?view=semantic-link-python#sempy-fabric-model-memory-analyzer)" function used in this notebook is just one example of the useful [functions]((https://learn.microsoft.com/python/api/semantic-link-sempy/sempy.fabric)) which Semantic Link offers.
# 
# You can find more [functions](https://github.com/microsoft/semantic-link-labs#featured-scenarios) and [helper notebooks](https://github.com/microsoft/semantic-link-labs/tree/main/notebooks) in [Semantic Link Labs](https://github.com/microsoft/semantic-link-labs), a Python library that extends Semantic Link's capabilities to automate technical tasks.
# 
# ### Low-code solutions for data tasks
# You don't have to be a Python expert to use Semantic Link or Semantic Link Labs. Many functions can be used simply by entering your parameters and running the notebook.


# MARKDOWN ********************

# #### Import the Semantic Link library

# CELL ********************

import sempy.fabric as fabric

dataset = "semantic_model_oeminsightbi" # Enter the name or ID of the semantic model
workspace = "OEMMatInsightBI" # Enter the workspace name or ID in which the semantic model exists

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# #### Run the Memory Analyzer on your semantic model

# CELL ********************

# --- 1. Fetch the metadata using specific functions ---

# Get a DataFrame of all tables in the semantic model
tables_df = fabric.list_tables(dataset=dataset, workspace=workspace)

# Get a DataFrame of all columns
columns_df = fabric.list_columns(dataset=dataset, workspace=workspace)

# Get a DataFrame of all active relationships
relationships_df = fabric.list_relationships(dataset=dataset, workspace=workspace)

# Get a DataFrame of all DAX measures
measures_df = fabric.list_measures(dataset=dataset, workspace=workspace)

# (Optional) You can display one of the dataframes to see what it looks like
print("--- Sample of Columns DataFrame ---")
display(columns_df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# --- 2. (CORRECTED) Format the metadata into a single text block ---

context_string = "### Semantic Model Context ###\n\n"

# Format Schema (Tables and Columns)
context_string += "--- SCHEMA ---\n"
# We iterate through tables first to keep columns grouped by table
for index, table_row in tables_df.iterrows():
    # CORRECTED: The column is named 'Name', not 'Table Name'
    table_name = table_row['Name'] 
    context_string += f"\nTable: '{table_name}'\n"
    
    # Filter the columns DataFrame for the current table
    table_columns = columns_df[columns_df['Table Name'] == table_name]
    for _, col_row in table_columns.iterrows():
        col_name = col_row['Column Name']
        col_dtype = col_row['Data Type']
        context_string += f"  - {col_name} ({col_dtype})\n"

# Format Relationships
context_string += "\n--- RELATIONSHIPS ---\n"
for index, rel_row in relationships_df.iterrows():
    from_table = rel_row['From Table']
    from_col = rel_row['From Column']
    to_table = rel_row['To Table']
    to_col = rel_row['To Column']
    context_string += f"'{from_table}'[{from_col}] -> '{to_table}'[{to_col}]\n"

# Format Measures
if not measures_df.empty:
    context_string += "\n--- DAX MEASURES ---\n"
    for index, measure_row in measures_df.iterrows():
        table_name = measure_row['Table Name']
        measure_name = measure_row['Measure Name']
        expression = measure_row['Measure Expression']
        context_string += f"Measure in '{table_name}':\n"
        context_string += f"[{measure_name}] = {expression}\n\n"

# Print the final context package to the screen
print(context_string)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# --- 3. Save the context string to a file in your Lakehouse ---

file_name = "llm_model_context.txt"
file_path = f"/lakehouse/default/Files/{file_name}"

with open(file_path, "w") as f:
    f.write(context_string)

print(f"Successfully saved context to '{file_name}' in your Lakehouse Files.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# #### Learn more about notebooks in Fabric
# Notebooks in Fabric empower you to use code and low-code solutions for a wide range of data analytics and data engineering tasks such as data transformation, pipeline automation, and machine learning modeling.
# 
# * To edit this notebook, switch the mode from **Run** only to **Edit** or **Develop**.
# * You can safely delete this notebook after running it. This won’t affect your semantic model.
# * This notebook uses Python, which is currently a preview experience. For a General Availability experience, you can change the language to PySpark from the language dropdown menu in the Home tab.
# 
# 
# For more information on capabilities and features, check out [Microsoft Fabric Notebook Documentation](https://learn.microsoft.com/fabric/data-engineering/how-to-use-notebook).

