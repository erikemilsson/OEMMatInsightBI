[StagingDefinition = [Kind = "FastCopy"]]
section Section1;
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "epi2024results csv_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared #"epi2024results csv" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "Files", ItemKind = "Folder"]}[Data],
  #"Navigation 3" = #"Navigation 2"{[Name = "EPI"]}[Content],
  #"Navigation 4" = #"Navigation 3"{[Name = "epi2024results.csv"]}[Content],
  #"Imported CSV" = Csv.Document(#"Navigation 4", [Delimiter = ",", Columns = 149, QuoteStyle = QuoteStyle.None]),
  #"Promoted headers" = Table.PromoteHeaders(#"Imported CSV", [PromoteAllScalars = true])
in
  #"Promoted headers";
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "epi2024variables2024-12-11 csv_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared #"epi2024variables2024-12-11 csv" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "Files", ItemKind = "Folder"]}[Data],
  #"Navigation 3" = #"Navigation 2"{[Name = "EPI"]}[Content],
  #"Navigation 4" = #"Navigation 3"{[Name = "epi2024variables2024-12-11.csv"]}[Content],
  #"Imported CSV" = Csv.Document(#"Navigation 4", [Delimiter = ",", Columns = 7, Encoding = 65001, QuoteStyle = QuoteStyle.None]),
  #"Promoted headers" = Table.PromoteHeaders(#"Imported CSV", [PromoteAllScalars = true])
in
  #"Promoted headers";
shared #"epi2024results csv_DataDestination" = let
  Pattern = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  TableNavigation = Navigation_2{[Id = "bronze_epi2024results", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
shared #"epi2024variables2024-12-11 csv_DataDestination" = let
  Pattern = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  TableNavigation = Navigation_2{[Id = "bronze_epi2024variables2024-12-11", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
