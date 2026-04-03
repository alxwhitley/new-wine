"use client";

import Link from "next/link";
import { SearchDocument } from "@/lib/api";
import { BookOpen } from "lucide-react";

interface DocumentCardProps {
  document: SearchDocument;
}

export default function DocumentCard({ document }: DocumentCardProps) {
  return (
    <Link href={`/document/${document.id}`}>
      <div
        style={{
          borderRadius: "10px",
          padding: "18px",
          background: "#262624",
          border: "1px solid #2a2a28",
          cursor: "pointer",
          transition: "border-color 150ms",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "#b49238";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = "#2a2a28";
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
          <BookOpen
            size={16}
            strokeWidth={1.8}
            style={{ flexShrink: 0, marginTop: "2px", color: "#d4b96a" }}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3
              style={{
                fontSize: "14px",
                fontWeight: 600,
                fontFamily: "var(--font-lora), Lora, serif",
                color: "#e6e6e6",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {document.title}
            </h3>
            <p style={{ fontSize: "12px", color: "#c1c1b8", marginTop: "4px" }}>
              {document.author}
              {document.year ? ` · ${document.year}` : ""}
              {document.source_type ? ` · ${document.source_type}` : ""}
            </p>
            {document.topic_tags && document.topic_tags.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "10px" }}>
                {document.topic_tags.map((tag) => (
                  <span
                    key={tag}
                    style={{
                      fontSize: "11px",
                      padding: "2px 8px",
                      borderRadius: "6px",
                      background: "#3c3c38",
                      color: "#c1c1b8",
                    }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
