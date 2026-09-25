/*
 * The page a fresh installation shows when this browser may not claim it.
 *
 * This replaced a one-line "registration is disabled" alert that gave an operator
 * nothing to act on — the dead end reported from an Unraid install in #248. Each
 * reason has to name a change the operator can make in their deployment, and the
 * environment administrator has to be offered in every case: it is the one exit
 * that works behind a proxy PrintStash cannot see through.
 */
import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SetupUnavailable } from "@/components/setup-unavailable";
import { renderApp } from "@/test-support/render";
import type { SetupStatus } from "@/types";

function renderPage(
  reason: NonNullable<SetupStatus["unavailable_reason"]>,
  onRetry = vi.fn<() => void>(),
) {
  return renderApp(<SetupUnavailable reason={reason} host="vault.example.net" onRetry={onRetry} />);
}

function exits() {
  return within(screen.getByRole("list", { name: "Ways to continue" }));
}

describe("SetupUnavailable", () => {
  it("names the host it refused", () => {
    renderPage("untrusted_host");

    expect(screen.getByRole("alert")).toHaveTextContent("vault.example.net");
  });

  it("offers the refused host as an allowed hostname", () => {
    renderPage("untrusted_host");

    expect(exits().getByText("VAULT_SETUP_ALLOWED_HOSTS=vault.example.net")).toBeVisible();
  });

  it("offers the local network address for an untrusted host", () => {
    renderPage("untrusted_host");

    expect(exits().getByText(/local network address/)).toBeVisible();
  });

  it("offers turning on registration when it is disabled", () => {
    renderPage("disabled");

    expect(exits().getByText("VAULT_SETUP_MODE=trusted_network")).toBeVisible();
  });

  it("does not suggest another address when registration is disabled", () => {
    renderPage("disabled");

    expect(exits().queryByText(/VAULT_SETUP_ALLOWED_HOSTS/)).not.toBeInTheDocument();
  });

  it.each([{ reason: "disabled" as const }, { reason: "untrusted_host" as const }])(
    "offers the environment administrator for $reason",
    ({ reason }) => {
      renderPage(reason);

      expect(exits().getByText(/VAULT_SETUP_ADMIN_USERNAME=/)).toBeVisible();
    },
  );

  it("checks again on request", async () => {
    const onRetry = vi.fn<() => void>();
    renderPage("untrusted_host", onRetry);

    await userEvent.click(screen.getByRole("button", { name: "Check again" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});
