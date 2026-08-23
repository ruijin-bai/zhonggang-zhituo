"use client";

export default function PrintButton() {
  return (
    <button className="secondary-button" type="button" onClick={() => window.print()}>
      打印 / 保存 PDF
    </button>
  );
}
