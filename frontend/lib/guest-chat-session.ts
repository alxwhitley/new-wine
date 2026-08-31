import type { Citation } from "./api";
import type { VerifiedReference } from "./study-reference";

export const GUEST_CHAT_SESSION_KEY = "newwine_guest_chat_v1";

export interface GuestChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  messageId?: string | null;
  verifiedReferences?: VerifiedReference[];
  quoteIds?: string[];
}

export interface PendingGuestJob {
  jobId: string;
  question: string;
}

export interface GuestChatSession {
  version: 1;
  messages: GuestChatMessage[];
  topicsEstablished: Record<string, number>;
  pendingJob: PendingGuestJob | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCitation(value: unknown): value is Citation {
  if (!isRecord(value)) return false;
  if (
    typeof value.chunk_id !== "string"
    || typeof value.document_title !== "string"
    || typeof value.author !== "string"
    || typeof value.content !== "string"
  ) return false;
  if (value.url === undefined || value.url === null) return true;
  if (typeof value.url !== "string") return false;
  try {
    const url = new URL(value.url);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function isVerifiedReference(value: unknown): value is VerifiedReference {
  if (!isRecord(value) || typeof value.type !== "string" || typeof value.raw !== "string") return false;
  if (value.positions !== undefined && (
    !Array.isArray(value.positions) || value.positions.some((position) => typeof position !== "number")
  )) return false;
  if (value.position !== undefined && typeof value.position !== "number") return false;
  if (value.source_id !== undefined && typeof value.source_id !== "string") return false;
  return true;
}

function isMessage(value: unknown): value is GuestChatMessage {
  if (!isRecord(value)) return false;
  if (value.role !== "user" && value.role !== "assistant") return false;
  if (typeof value.content !== "string") return false;
  if (value.citations !== undefined && (
    !Array.isArray(value.citations) || !value.citations.every(isCitation)
  )) return false;
  if (value.verifiedReferences !== undefined && (
    !Array.isArray(value.verifiedReferences) || !value.verifiedReferences.every(isVerifiedReference)
  )) return false;
  if (value.quoteIds !== undefined && (
    !Array.isArray(value.quoteIds) || value.quoteIds.some((id) => typeof id !== "string")
  )) return false;
  if (value.messageId !== undefined && value.messageId !== null && typeof value.messageId !== "string") return false;
  return true;
}

function isTopics(value: unknown): value is Record<string, number> {
  return isRecord(value) && Object.values(value).every((turn) => (
    typeof turn === "number" && Number.isFinite(turn)
  ));
}

function isPendingJob(value: unknown): value is PendingGuestJob | null {
  if (value === null) return true;
  return isRecord(value)
    && typeof value.jobId === "string"
    && value.jobId.length > 0
    && typeof value.question === "string"
    && value.question.length > 0;
}

export function parseGuestChatSession(raw: string | null): GuestChatSession | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || value.version !== 1) return null;
    if (!Array.isArray(value.messages) || !value.messages.every(isMessage)) return null;
    if (!isTopics(value.topicsEstablished) || !isPendingJob(value.pendingJob)) return null;
    return value as unknown as GuestChatSession;
  } catch {
    return null;
  }
}

export function serializeGuestChatSession(session: GuestChatSession): string {
  return JSON.stringify(session);
}

export function shouldRetainPendingGuestJob(error: string): boolean {
  return !error.startsWith("generation_")
    && error !== "job_disappeared"
    && error !== "result_404";
}
