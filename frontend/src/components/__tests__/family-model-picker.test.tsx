/** A family model picker must show mounted folder names, not collection slugs. */
import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { FamilyModelPicker, type FamilyPickerModel } from "@/components/families/model-picker";
import { queryKeys } from "@/lib/query-client";
import { aCollection, aModelListItem } from "@/test-support/factories";
import { json, renderApp } from "@/test-support/render";

it("shows the disk folder names when choosing a model for a family", async () => {
  const collections = [
    aCollection({ id: 1, name: "Testing", slug: "testing", path: "testing" }),
    aCollection({
      id: 2,
      name: "My Parts",
      slug: "my-parts",
      path: "testing/my-parts",
      parent_id: 1,
    }),
  ];
  renderApp(
    <FamilyModelPicker
      selected={new Map()}
      onToggle={vi.fn<(model: FamilyPickerModel) => void>()}
    />,
    {
      seed: [[queryKeys.collections, collections]],
      routes: {
        "GET /api/v1/models/page": json({
          items: [aModelListItem({ name: "Cam Holder", collection: "testing/my-parts" })],
          next_cursor: null,
          total: 1,
        }),
      },
    },
  );

  expect(await screen.findByText("Testing/My Parts")).toBeVisible();
  expect(screen.queryByText("testing/my-parts")).toBeNull();
});
