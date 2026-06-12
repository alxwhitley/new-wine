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

export interface NotCondition {
  col: string;
  val: string;
}

export interface CorpusCard {
  id: string;
  name: string;
  group: string;
  status: StatusBadge;
  description: string;
  sourceKind?: string;
  sourceType?: string;
  extraFilter?: string;
  notFilter?: NotCondition[];
  specialTable?: string;
  specialWhere?: string;
  countChunks?: boolean;
  countLabel?: string;
  steps?: PipelineStep[];
  commands: Command[];
  bookList?: BookEntry[];
  progressTarget?: number;
  isMaintenance?: boolean;
}

export interface CorpusCount {
  cardId: string;
  count: number;
  lastIngested: string | null;
}

export interface FutureTarget {
  id: string;
  name: string;
  description: string;
  urls: string[];
}
