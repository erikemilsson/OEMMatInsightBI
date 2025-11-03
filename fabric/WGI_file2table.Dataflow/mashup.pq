[DefaultOutputDestinationSettings = [DestinationDefinition = [Kind = "Reference", QueryName = "DefaultDestination", IsNewTarget = true], UpdateMethod = [Kind = "Replace"], DestinationTypeSettings = [Kind = "Table"]], StagingDefinition = [Kind = "FastCopy"]]
section Section1;
shared DefaultDestination = let
  Source = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  #"Navigation 1" = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data]
in
  #"Navigation 2";
[BindToDefaultDestination = true]
shared bronze_WGI = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "Files", ItemKind = "Folder"]}[Data],
  #"Navigation 3" = #"Navigation 2"{[Name = "WGI"]}[Content],
  #"Navigation 4" = #"Navigation 3"{[Name = "P_Data_Extract_From_Worldwide_Governance_Indicators.xlsx"]}[Content],
  #"Imported Excel workbook" = Excel.Workbook(#"Navigation 4", null, true),
  #"Navigation 5" = #"Imported Excel workbook"{[Item = "Data", Kind = "Sheet"]}[Data],
  #"Changed column type" = Table.TransformColumnTypes(#"Navigation 5", {{"Column1", type text}, {"Column2", type text}, {"Column3", type text}, {"Column4", type text}}),
  #"Promoted headers" = Table.PromoteHeaders(#"Changed column type", [PromoteAllScalars = true]),
  #"Renamed columns" = Table.RenameColumns(#"Promoted headers", {{"2023 [YR2023]", "Percentile Rank 2023"}}),
  #"Removed other columns" = Table.SelectColumns(#"Renamed columns", {"Country Name", "Country Code", "Series Name", "Percentile Rank 2023"}),
  #"Replaced value" = Table.ReplaceValue(#"Removed other columns", ": Percentile Rank", "", Replacer.ReplaceText, {"Series Name"})
in
  #"Replaced value";
