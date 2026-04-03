"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, BookOpen } from "lucide-react";
import { getDocument, Document, Chunk } from "@/lib/api";

export default function DocumentPage() {
  const params = useParams<{ id: string }>();
  const [document, setDocument] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.id) return;
    setLoading(true);
    getDocument(params.id)
      .then((res) => {
        setDocument(res.document);
        setChunks(res.chunks);
      })
      .catch(() => setError("Failed to load document"))
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "#1f1e1d",
        }}
      >
        <p style={{ fontSize: "14px", color: "#c1c1b8" }}>Loading...</p>
      </div>
    );
  }

  if (error || !document) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          gap: "16px",
          background: "#1f1e1d",
        }}
      >
        <p style={{ fontSize: "14px", color: "#e57373" }}>
          {error || "Document not found"}
        </p>
        <Link
          href="/"
          style={{ fontSize: "13px", color: "#d4b96a" }}
        >
          Back to home
        </Link>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "#1f1e1d" }}>
      <div style={{ maxWidth: "620px", margin: "0 auto", padding: "40px 32px" }}>
        <Link
          href="/"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "13px",
            color: "#c1c1b8",
            marginBottom: "40px",
            transition: "color 150ms",
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = "#b49238"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = "#c1c1b8"; }}
        >
          <ArrowLeft size={14} strokeWidth={1.8} />
          Back
        </Link>

        <div style={{ display: "flex", alignItems: "flex-start", gap: "14px", marginBottom: "8px" }}>
          <BookOpen
            size={22}
            strokeWidth={1.8}
            style={{ flexShrink: 0, marginTop: "4px", color: "#d4b96a" }}
          />
          <div>
            <h1
              style={{
                fontSize: "24px",
                fontWeight: 600,
                lineHeight: 1.3,
                fontFamily: "var(--font-lora), Lora, serif",
                color: "#e6e6e6",
              }}
            >
              {document.title}
            </h1>
            <p style={{ fontSize: "14px", color: "#c1c1b8", marginTop: "6px" }}>
              {document.author}
              {document.year ? ` · ${document.year}` : ""}
              {document.source_type ? ` · ${document.source_type}` : ""}
            </p>
          </div>
        </div>

        {document.topic_tags && document.topic_tags.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "6px",
              marginTop: "20px",
              marginBottom: "40px",
              marginLeft: "36px",
            }}
          >
            {document.topic_tags.map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: "11px",
                  padding: "2px 8px",
                  borderRadius: "6px",
                  background: "#262624",
                  color: "#c1c1b8",
                  border: "1px solid #2a2a28",
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: "14px", marginTop: "32px" }}>
          {chunks.map((chunk) => (
            <div
              key={chunk.id}
              style={{
                borderRadius: "10px",
                padding: "22px",
                fontSize: "14px",
                lineHeight: "1.8",
                background: "#262624",
                color: "#e6e6e6",
              }}
            >
              {chunk.content}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
