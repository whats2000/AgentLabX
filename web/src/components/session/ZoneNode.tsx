const ZONE_COLOR: Record<string, string> = {
  discovery: "rgba(24, 144, 255, 0.06)",
  implementation: "rgba(250, 173, 20, 0.06)",
  synthesis: "rgba(82, 196, 26, 0.06)",
};

export function ZoneNode({ data }: { data: { zone: string } }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: ZONE_COLOR[data.zone] ?? "#fafafa",
        border: "1px dashed #ccc",
        borderRadius: 8,
        padding: 4,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          color: "#666",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {data.zone}
      </div>
    </div>
  );
}
