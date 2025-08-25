[StagingDefinition = [Kind = "FastCopy"]]
section Section1;
shared silver_epi2024results = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "silver_epi2024results", ItemKind = "Table"]}[Data],
  #"Unpivoted other columns" = Table.UnpivotOtherColumns(#"Navigation 2", {"code", "iso", "country"}, "Attribute", "Value"),
  #"Renamed columns" = Table.RenameColumns(#"Unpivoted other columns", {{"Attribute", "indicator"}, {"Value", "score"}})
in
  #"Renamed columns";
shared #"silver_epi2024variables2024-12-11" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "silver_epi2024variables2024-12-11", ItemKind = "Table"]}[Data]
in
  #"Navigation 2";
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "Global Share_DataDestination", IsNewTarget = true], Settings = [Kind = "Manual", AllowCreation = true, ColumnSettings = [Mappings = {[SourceColumnName = "material", DestinationColumnName = "material"], [SourceColumnName = "stage", DestinationColumnName = "stage"], [SourceColumnName = "country", DestinationColumnName = "country"], [SourceColumnName = "countryshare", DestinationColumnName = "countryshare"]}], DynamicSchema = false, UpdateMethod = [Kind = "Replace"], TypeSettings = [Kind = "Table"]]]}]
shared #"Global Share" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "silver_globalsupplyshares", ItemKind = "Table"]}[Data],
  #"Removed columns" = Table.RemoveColumns(#"Navigation 2", {"t"}),
  #"Replaced value" = Table.ReplaceValue(#"Removed columns", "<", "", Replacer.ReplaceText, {"share"}),
  #"Replaced value 1" = Table.ReplaceValue(#"Replaced value", ">", "", Replacer.ReplaceText, {"share"}),
  #"Replaced value 2" = Table.ReplaceValue(#"Replaced value 1", "%", "", Replacer.ReplaceText, {"share"}),
  #"Changed column type" = Table.TransformColumnTypes(#"Replaced value 2", {{"share", type number}}),
  #"Inserted division" = Table.AddColumn(#"Changed column type", "Division", each [share] / 100, type number),
  #"Changed column type 1" = Table.TransformColumnTypes(#"Inserted division", {{"Division", Percentage.Type}}),
  #"Renamed columns" = Table.RenameColumns(#"Changed column type 1", {{"Division", "countryshare"}}),
  #"Removed columns 1" = Table.RemoveColumns(#"Renamed columns", {"share"}),
  #"Replaced value 3" = Table.ReplaceValue(#"Removed columns 1", "E", "Extraction", Replacer.ReplaceText, {"stage"}),
  #"Replaced value 4" = Table.ReplaceValue(#"Replaced value 3", "P", "Processing", Replacer.ReplaceText, {"stage"})
in
  #"Replaced value 4";
shared silver_wb = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "silver_wb", ItemKind = "Table"]}[Data],
  #"Removed other columns" = Table.SelectColumns(#"Navigation 2", {"topic", "score", "indicator_name", "country_code"}),
  #"Added custom" = Table.TransformColumnTypes(Table.AddColumn(#"Removed other columns", "source", each "World Bank"), {{"source", type text}}),
  #"Renamed columns" = Table.RenameColumns(#"Added custom", {{"indicator_name", "variable"}, {"country_code", "country-iso"}})
in
  #"Renamed columns";
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "Indicators_DataDestination", IsNewTarget = true], Settings = [Kind = "Manual", AllowCreation = true, ColumnSettings = [Mappings = {[SourceColumnName = "country-iso", DestinationColumnName = "country-iso"], [SourceColumnName = "country", DestinationColumnName = "country"], [SourceColumnName = "indicator", DestinationColumnName = "indicator"], [SourceColumnName = "score", DestinationColumnName = "score"], [SourceColumnName = "type", DestinationColumnName = "type"], [SourceColumnName = "abbreviation", DestinationColumnName = "abbreviation"], [SourceColumnName = "variable", DestinationColumnName = "variable"], [SourceColumnName = "topic", DestinationColumnName = "topic"], [SourceColumnName = "policyobjective", DestinationColumnName = "policyobjective"], [SourceColumnName = "weight", DestinationColumnName = "weight"], [SourceColumnName = "description", DestinationColumnName = "description"], [SourceColumnName = "source", DestinationColumnName = "source"]}], DynamicSchema = false, UpdateMethod = [Kind = "Replace"], TypeSettings = [Kind = "Table"]]]}]
shared Indicators = let
  Source = Table.NestedJoin(silver_epi2024results, {"indicator"}, #"silver_epi2024variables2024-12-11", {"abbreviation"}, "silver_epi2024variables2024-12-11", JoinKind.LeftOuter),
  #"Removed columns" = Table.RemoveColumns(Source, {"code"}),
  #"Added custom" = Table.TransformColumnTypes(Table.AddColumn(#"Removed columns", "source", each "EPI"), {{"source", type text}}),
  #"Expanded silver_epi2024variables2024-12-11" = Table.ExpandTableColumn(#"Added custom", "silver_epi2024variables2024-12-11", {"type", "abbreviation", "variable", "issuecategory", "policyobjective", "weight", "description"}, {"type", "abbreviation", "variable", "issuecategory", "policyobjective", "weight", "description"}),
  #"Renamed columns" = Table.RenameColumns(#"Expanded silver_epi2024variables2024-12-11", {{"iso", "country-iso"}, {"issuecategory", "topic"}}),
  #"Appended query" = Table.Combine({#"Renamed columns", silver_wb})
in
  #"Appended query";
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "Procurement Hit_DataDestination", IsNewTarget = true], Settings = [Kind = "Manual", AllowCreation = true, ColumnSettings = [Mappings = {[SourceColumnName = "productioncountry", DestinationColumnName = "productioncountry"], [SourceColumnName = "materialname", DestinationColumnName = "materialname"], [SourceColumnName = "total_kg", DestinationColumnName = "total_kg"]}], DynamicSchema = false, UpdateMethod = [Kind = "Replace"], TypeSettings = [Kind = "Table"]]]}]
shared #"Procurement Hit" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "silver_procurement", ItemKind = "Table"]}[Data],
  #"Filtered rows" = Table.SelectRows(#"Navigation 2", each ([unit] = "kg")),
  #"Removed columns" = Table.RemoveColumns(#"Filtered rows", {"headquarterscountry", "unit", "unitpriceeur"}),
  #"Renamed columns" = Table.RenameColumns(#"Removed columns", {{"quantity", "kg"}}),
  #"Removed columns 1" = Table.RemoveColumns(#"Renamed columns", {"date"}),
  #"Changed column type" = Table.TransformColumnTypes(#"Removed columns 1", {{"kg", type number}}),
  #"Reordered columns" = Table.ReorderColumns(#"Changed column type", {"materialname", "productioncountry", "kg"}),
  #"Grouped rows" = Table.Group(#"Reordered columns", {"productioncountry", "materialname"}, {{"total_kg", each List.Sum([kg]), type nullable number}})
in
  #"Grouped rows";
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "Procurement Miss_DataDestination", IsNewTarget = true], Settings = [Kind = "Manual", AllowCreation = true, ColumnSettings = [Mappings = {[SourceColumnName = "materialname", DestinationColumnName = "materialname"], [SourceColumnName = "productioncountry", DestinationColumnName = "productioncountry"], [SourceColumnName = "total_pieces", DestinationColumnName = "total_pieces"]}], DynamicSchema = false, UpdateMethod = [Kind = "Replace"], TypeSettings = [Kind = "Table"]]]}]
shared #"Procurement Miss" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "silver_procurement", ItemKind = "Table"]}[Data],
  #"Filtered rows" = Table.SelectRows(#"Navigation 2", each ([unit] = "pcs")),
  #"Renamed columns" = Table.RenameColumns(#"Filtered rows", {{"quantity", "pieces"}}),
  #"Removed columns" = Table.RemoveColumns(#"Renamed columns", {"unit", "date", "unitpriceeur", "headquarterscountry"}),
  #"Reordered columns" = Table.ReorderColumns(#"Removed columns", {"materialname", "productioncountry", "pieces"}),
  #"Changed column type" = Table.TransformColumnTypes(#"Reordered columns", {{"pieces", type number}}),
  #"Grouped rows" = Table.Group(#"Changed column type", {"materialname", "productioncountry"}, {{"total_pieces", each List.Sum([pieces]), type nullable text}}),
  #"Changed column type 1" = Table.TransformColumnTypes(#"Grouped rows", {{"total_pieces", type number}})
in
  #"Changed column type 1";
shared Indicators_DataDestination = let
  Pattern = Fabric.Warehouse([CreateNavigationProperties = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[warehouseId = "b1cb7506-8d2d-4e4a-97cc-2b580da8eda0"]}[Data],
  TableNavigation = Navigation_2{[Item = "golddim_Indicators", Schema = "dbo"]}?[Data]?
in
  TableNavigation;
shared #"Global Share_DataDestination" = let
  Pattern = Fabric.Warehouse([CreateNavigationProperties = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[warehouseId = "b1cb7506-8d2d-4e4a-97cc-2b580da8eda0"]}[Data],
  TableNavigation = Navigation_2{[Item = "golddim_globalshare", Schema = "dbo"]}?[Data]?
in
  TableNavigation;
shared #"Procurement Hit_DataDestination" = let
  Pattern = Fabric.Warehouse([CreateNavigationProperties = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[warehouseId = "b1cb7506-8d2d-4e4a-97cc-2b580da8eda0"]}[Data],
  TableNavigation = Navigation_2{[Item = "golddim_procurementhit", Schema = "dbo"]}?[Data]?
in
  TableNavigation;
shared #"Procurement Miss_DataDestination" = let
  Pattern = Fabric.Warehouse([CreateNavigationProperties = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[warehouseId = "b1cb7506-8d2d-4e4a-97cc-2b580da8eda0"]}[Data],
  TableNavigation = Navigation_2{[Item = "golddim_procurementMiss", Schema = "dbo"]}?[Data]?
in
  TableNavigation;
