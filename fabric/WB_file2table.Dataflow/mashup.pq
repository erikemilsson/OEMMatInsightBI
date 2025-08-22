[DefaultOutputDestinationSettings = [DestinationDefinition = [Kind = "Reference", QueryName = "DefaultDestination", IsNewTarget = true], UpdateMethod = [Kind = "Replace"], DestinationTypeSettings = [Kind = "Table"]], StagingDefinition = [Kind = "FastCopy"]]
section Section1;
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "WB_ESGCSV csv_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared #"WB_ESGCSV csv" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "Files", ItemKind = "Folder"]}[Data],
  #"Navigation 3" = #"Navigation 2"{[Name = "WB"]}[Content],
  #"Navigation 4" = #"Navigation 3"{[Name = "WB_ESGCSV.csv"]}[Content],
  #"Imported CSV" = Csv.Document(#"Navigation 4", [Delimiter = ",", Columns = 68, QuoteStyle = QuoteStyle.None]),

  // 1) Use first row as headers
  #"Promoted Headers" = Table.PromoteHeaders(#"Imported CSV", [PromoteAllScalars = true]),

  // 2) Prefix headers that start with a digit (e.g., 1960 -> y_1960)
  Prefix = "y_",
  Digits = List.Transform({0..9}, Text.From),
  PrefixIfDigit = (n as text) as text =>
      if List.Contains(Digits, Text.Start(n, 1)) then Prefix & n else n,
  #"Prefixed Numeric Headers" = Table.TransformColumnNames(#"Promoted Headers", PrefixIfDigit)
in
  #"Prefixed Numeric Headers";
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "WB_ESGCountry csv_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared #"WB_ESGCountry csv" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "Files", ItemKind = "Folder"]}[Data],
  #"Navigation 3" = #"Navigation 2"{[Name = "WB"]}[Content],
  #"Navigation 4" = #"Navigation 3"{[Name = "WB_ESGCountry.csv"]}[Content],
  #"Imported CSV" = Csv.Document(#"Navigation 4", [Delimiter = ",", Columns = 31, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
  #"Promoted Headers" = Table.PromoteHeaders(#"Imported CSV", [PromoteAllScalars=true]),
    Prefix = "_",                                  
    Digits = List.Transform({0..9}, Text.From),
    PrefixIfDigit = (n as text) as text =>
      if List.Contains(Digits, Text.Start(n, 1)) then Prefix & n else n,
  #"Prefixed Numeric Headers" =
      Table.TransformColumnNames(#"Promoted Headers", PrefixIfDigit)
in
  #"Prefixed Numeric Headers";
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "WB_ESGSeries csv_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared #"WB_ESGSeries csv" = let
  Source = Lakehouse.Contents(null),
  Navigation = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 1" = Navigation{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Id = "Files", ItemKind = "Folder"]}[Data],
  #"Navigation 3" = #"Navigation 2"{[Name = "WB"]}[Content],
  #"Navigation 4" = #"Navigation 3"{[Name = "WB_ESGSeries.csv"]}[Content],
  #"Imported CSV" = Csv.Document(#"Navigation 4", [Delimiter = ",", Columns = 20, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
  #"Promoted headers" = Table.PromoteHeaders(#"Imported CSV", [PromoteAllScalars = true])
in
  #"Promoted headers";
shared #"WB_ESGCountry csv_DataDestination" = let
  Pattern = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  TableNavigation = Navigation_2{[Id = "bronze_WB_ESGCountry", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
shared #"WB_ESGSeries csv_DataDestination" = let
  Pattern = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  TableNavigation = Navigation_2{[Id = "bronze_WB_ESGSeries", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
shared #"WB_ESGCSV csv_DataDestination" = let
  Pattern = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data],
  TableNavigation = Navigation_2{[Id = "bronze_WB_ESGCSV", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
shared DefaultDestination = let
  Source = Lakehouse.Contents([CreateNavigationProperties = false, EnableFolding = false]),
  #"Navigation 1" = Source{[workspaceId = "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[lakehouseId = "488fb9f8-e635-4683-90c4-ba4fee9dfadb"]}[Data]
in
  #"Navigation 2";
