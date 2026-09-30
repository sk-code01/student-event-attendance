export type ReportFormat = 'csv' | 'xlsx' | 'pdf';

/** A report type the backend says this caller may run. The list is advisory;
 * the export endpoint re-checks authorization independently. */
export interface ReportType {
  key: string;
  title: string;
  description: string;
  formats: ReportFormat[];
}

/** A JSON preview of exactly the rows the exported file will contain. */
export interface ReportDataset {
  key: string;
  title: string;
  description: string;
  columns: string[];
  rows: string[][];
  row_count: number;
  filters: string;
}
