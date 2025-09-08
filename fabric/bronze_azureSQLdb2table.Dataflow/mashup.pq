[StagingDefinition = [Kind = "FastCopy"]]
section Section1;
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "procurement_transactional_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared procurement_transactional = let
  Source = Sql.Database("procurement-supplier.database.windows.net", "procurement-supplier-db", [EnableCrossDatabaseFolding = true]),
  #"Navigation 1" = Source{[Schema = "dbo", Item = "procurement_transactional"]}[Data],
  #"Changed column type" = Table.TransformColumnTypes(#"Navigation 1", {{"Date", type text}}),
  #"Changed column type 1" = Table.TransformColumnTypes(#"Changed column type", {{"Date", type date}}, "en-US"),
  #"Added custom" = Table.TransformColumnTypes(Table.AddColumn(#"Changed column type 1", "CorrectedDate", each #date(
    Date.Day([Date]) + 2000, 
    Date.Month([Date]), 
    Date.Year([Date]) - 2000
)), {{"CorrectedDate", type date}}),
  #"Reordered columns" = Table.ReorderColumns(#"Added custom", {"Date", "CorrectedDate", "MaterialName", "SupplierName", "Region", "Quantity", "Unit", "UnitPriceEUR"}),
  #"Removed columns" = Table.RemoveColumns(#"Reordered columns", {"Date"}),
  #"Renamed columns" = Table.RenameColumns(#"Removed columns", {{"CorrectedDate", "Date"}})
in
  #"Renamed columns";
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "supplier_ref_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared supplier_ref = let
  Source = Sql.Database("procurement-supplier.database.windows.net", "procurement-supplier-db", [EnableCrossDatabaseFolding = true]),
  #"Navigation 1" = Source{[Schema = "dbo", Item = "supplier_ref"]}[Data]
in
  #"Navigation 1";
shared procurement_transactional_DataDestination = let
  Pattern = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  TableNavigation = Navigation_2{[Id = "bronze_procurement_transactional", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
shared supplier_ref_DataDestination = let
  Pattern = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  TableNavigation = Navigation_2{[Id = "bronze_supplier_ref", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
