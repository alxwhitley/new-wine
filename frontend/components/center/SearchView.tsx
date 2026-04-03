"use client";

import { SearchDocument, SearchChunk } from "@/lib/api";
import DocumentCard from "./DocumentCard";

interface SearchViewProps {
  query: string;
  documents: SearchDocument[];
  chunks: SearchChunk[];
  loading: boolean;
  error: string | null;
  hasSearched: boolean;
}

export default function SearchView({
  query,
  documents,
  chunks,
  loading,
  error,
  hasSearched,
}: SearchViewProps) {
  if (loading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: "14px", color: "#c1c1b8" }}>Searching...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: "14px", color: "#e57373" }}>{error}</p>
      </div>
    );
  }

  if (!hasSearched) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "4px",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--font-lora), Lora, serif",
            fontSize: "30px",
            fontWeight: 400,
            color: "#e6e6e6",
          }}
        >
          Search the library
        </h2>
        <p style={{ fontSize: "14px", color: "#c1c1b8" }}>
          Use the sidebar to search across all documents.
        </p>
      </div>
    );
  }

  if (documents.length === 0 && chunks.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "4px",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--font-lora), Lora, serif",
            fontSize: "22px",
            fontWeight: 400,
            color: "#e6e6e6",
          }}
        >
          No results
        </h2>
        <p style={{ fontSize: "14px", color: "#c1c1b8" }}>
          No documents matched &ldquo;{query}&rdquo;
        </p>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px 32px" }}>
      <div style={{ maxWidth: "620px", margin: "0 auto" }}>
        <p style={{ fontSize: "12px", color: "#c1c1b8", marginBottom: "20px" }}>
          {documents.length} document{documents.length !== 1 ? "s" : ""} found for &ldquo;{query}&rdquo;
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {documents.map((doc) => (
            <DocumentCard key={doc.id} document={doc} />
          ))}
        </div>
        {chunks.length > 0 && (
          <div style={{ marginTop: "32px" }}>
            <p
              style={{
                fontSize: "11px",
                fontWeight: 500,
                color: "#c1c1b8",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                marginBottom: "12px",
              }}
            >
              Matching passages
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {chunks.map((chunk) => (
                <div
                  key={chunk.id}
                  style={{
                    borderRadius: "10px",
                    padding: "20px",
                    fontSize: "14px",
                    lineHeight: "1.7",
                    background: "#262624",
                    border: "1px solid #2a2a28",
                    color: "#e6e6e6",
                  }}
                >
                  {chunk.content}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
