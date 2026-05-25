export type StatusBadge = "Complete" | "Ongoing" | "Not Started" | "Partial";

export interface Command {
  label: string;
  command: string;
}

export interface PipelineStep {
  label: string;
}

export interface BookEntry {
  author: string;
  titles: string[];
}

export interface CorpusCard {
  id: string;
  name: string;
  group: string;
  status: StatusBadge;
  description: string;
  sourceKind?: string;
  /** Filter on source_type instead of source_kind (e.g. books) */
  sourceType?: string;
  extraFilter?: string;
  /** For cards that query a different table entirely */
  specialTable?: string;
  /** For special table queries with a WHERE clause */
  specialWhere?: string;
  /** Count chunks instead of documents (e.g. lexicons) */
  countChunks?: boolean;
  /** Label for the count display (defaults to "documents") */
  countLabel?: string;
  steps?: PipelineStep[];
  commands: Command[];
  /** For Public Domain Books card */
  bookList?: BookEntry[];
  /** For Word Study Excerpts progress bar */
  progressTarget?: number;
  /** Maintenance cards: smaller, no count display */
  isMaintenance?: boolean;
}

export interface CorpusCount {
  cardId: string;
  count: number;
  lastIngested: string | null;
}
