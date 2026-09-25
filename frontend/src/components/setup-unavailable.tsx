import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/locale";

/**
 * Why this browser cannot claim the installation, and every way out.
 *
 * Browser registration refuses a host it cannot place on a private network
 * (that check is what stops a malicious page from claiming a LAN install
 * through DNS rebinding) or runs with registration turned off. Either way the
 * operator can still provision the first administrator from the deployment.
 */
export function SetupUnavailable({
  reason,
  host,
  onRetry,
}: {
  reason: "disabled" | "untrusted_host";
  host: string;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  const untrusted = reason === "untrusted_host";
  const exits: { key: MessageKey; code?: string }[] = untrusted
    ? [
        { key: "setup.unavailableLan" },
        { key: "setup.unavailableAllowHost", code: `VAULT_SETUP_ALLOWED_HOSTS=${host}` },
        { key: "setup.unavailableEnvAdmin", code: ENV_ADMIN },
      ]
    : [
        { key: "setup.unavailableEnable", code: "VAULT_SETUP_MODE=trusted_network" },
        { key: "setup.unavailableEnvAdmin", code: ENV_ADMIN },
      ];
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">
          {t(untrusted ? "setup.unavailableHostTitle" : "setup.unavailableDisabledTitle")}
        </h2>
        <p role="alert" className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {untrusted ? t("setup.unavailableHostHelp", { host }) : t("setup.disabled")}
        </p>
      </div>
      <ol
        aria-label={t("setup.unavailableExits")}
        className="list-decimal space-y-3 pl-5 text-sm leading-relaxed"
      >
        {exits.map((exit) => (
          <li key={exit.key}>
            {t(exit.key)}
            {exit.code && (
              <code className="mt-2 block select-all whitespace-pre-wrap break-all rounded bg-background px-3 py-2 font-mono text-xs text-foreground">
                {exit.code}
              </code>
            )}
          </li>
        ))}
      </ol>
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("setup.unavailableRestart")}
      </p>
      <Button variant="outline" onClick={onRetry}>
        {t("setup.unavailableRetry")}
      </Button>
    </div>
  );
}

const ENV_ADMIN = "VAULT_SETUP_ADMIN_USERNAME=admin\nVAULT_SETUP_ADMIN_PASSWORD=<your password>";
