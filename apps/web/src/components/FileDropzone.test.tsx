import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FileDropzone } from "./FileDropzone";

describe("FileDropzone", () => {
  it("accepts a supported document and can clear it", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(
      <FileDropzone id="document" label="Contract" file={null} onChange={onChange} />,
    );
    const file = new File(["contract"], "agreement.txt", { type: "text/plain" });

    await user.upload(screen.getByLabelText("Contract"), file);
    expect(onChange).toHaveBeenCalledWith(file);

    rerender(<FileDropzone id="document" label="Contract" file={file} onChange={onChange} />);
    expect(screen.getByText("agreement.txt")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remove agreement.txt" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("rejects an unsupported extension", () => {
    const onChange = vi.fn();
    render(<FileDropzone id="document" label="Contract" file={null} onChange={onChange} />);

    const file = new File(["data"], "agreement.csv", { type: "text/csv" });
    fireEvent.drop(screen.getByRole("button", { name: /choose or drop a document/i }), {
      dataTransfer: { files: [file] },
    });

    expect(screen.getByText("Choose a TXT, DOCX, or PDF file.")).toBeVisible();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("tracks drag state and accepts a dropped file", () => {
    const onChange = vi.fn();
    render(<FileDropzone id="document" label="Contract" file={null} onChange={onChange} />);
    const target = screen.getByRole("button", { name: /choose or drop a document/i });
    const file = new File(["terms"], "terms.pdf", { type: "application/pdf" });

    fireEvent.dragEnter(target);
    expect(target).toHaveClass("is-dragging");
    fireEvent.dragOver(target);
    fireEvent.dragLeave(target);
    expect(target).not.toHaveClass("is-dragging");

    fireEvent.drop(target, { dataTransfer: { files: [file] } });
    expect(onChange).toHaveBeenCalledWith(file);
  });
});
