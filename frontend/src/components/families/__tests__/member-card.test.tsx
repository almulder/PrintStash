/** Member measurements remain readable without inventing dimensions or source units. */
import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FamilyMemberCard } from "../member-card";
import { aMetadata, aRevision } from "@/test-support/factories";
import { aFamilyMember } from "@/test-support/families";
import { renderApp } from "@/test-support/render";

afterEach(() => vi.unstubAllGlobals());
describe("Family member dimensions", () => {
  it("keeps technical measurements behind details initially", () => {
    renderApp(
      <FamilyMemberCard
        member={aFamilyMember()}
        selected={false}
        selectionFull={false}
        editable={false}
        onToggle={() => {}}
        onAction={() => {}}
      />,
    );
    expect(screen.getByText("File and print details").closest("details")).not.toHaveAttribute(
      "open",
    );
  });
  it.each([
    { units: "mm" as const, suffix: "mm" },
    { units: "unknown" as const, suffix: "(units unknown)" },
  ])("labels $units dimensions honestly", ({ units, suffix }) => {
    renderApp(
      <FamilyMemberCard
        member={aFamilyMember({
          units,
          preview_file: aRevision({
            file_type: "stl",
            metadata: aMetadata({ bbox_x_mm: 60, bbox_y_mm: 31, bbox_z_mm: 48 }),
          }),
        })}
        selected={false}
        selectionFull={false}
        editable={false}
        onToggle={() => {}}
        onAction={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("File and print details"));
    expect(screen.getByText(`60 × 31 × 48 ${suffix}`)).toBeVisible();
  });
  it("keeps absent measurements unknown", () => {
    renderApp(
      <FamilyMemberCard
        member={aFamilyMember()}
        selected={false}
        selectionFull={false}
        editable={false}
        onToggle={() => {}}
        onAction={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("File and print details"));
    expect(screen.getByText("— × — × — (units unknown)")).toBeVisible();
  });
});
