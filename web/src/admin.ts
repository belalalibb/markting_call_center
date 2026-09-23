// Admin: tenants, capability registry, ephemeral test key (in-memory only; never persisted, never echoed).
import { api } from "./api";
import { clear, errMsg, h, pill, pre, section, table, toast, toneFor } from "./ui";

export async function renderAdmin(root: HTMLElement): Promise<void> {
  root.className = "";
  clear(root);
  root.append(tenantsCard(), testKeyCard(), registryCard());
}

function tenantsCard(): HTMLElement {
  const box = h("div");
  const card = section("Tenants", box);
  const draw = async () => {
    clear(box);
    const id = h("input", { placeholder: "tenant_id" });
    const name = h("input", { placeholder: "name" });
    const locale = h("input", { value: "ar-EG", placeholder: "default_locale" });
    box.append(h("div", { class: "row" }, id, name, locale, h("button", { class: "primary", onClick: async () => {
      try {
        await api.createTenant({ tenant_id: id.value, name: name.value, default_locale: locale.value });
        toast("tenant saved", "ok");
        await draw();
      } catch (e) { toast(errMsg(e), "bad"); }
    } }, "Create")));
    const ts = await api.tenants().catch(() => []);
    box.append(table(["id", "name", "status", "locale", "providers"], ts.map((t) => [
      h("code", {}, String(t.tenant_id)), String(t.name), pill(String(t.status), toneFor(String(t.status))), String(t.default_locale), (t.enabled_providers as string[]).join(", "),
    ])));
  };
  void draw();
  return card;
}

function testKeyCard(): HTMLElement {
  const box = h("div");
  const card = section("Ephemeral test key (Chat & Calls)", box);
  const draw = async () => {
    clear(box);
    const provider = h("select", {}, ...["openai", "mock", "deepgram", "elevenlabs"].map((p) => h("option", { value: p }, p)));
    const value = h("input", { type: "password", placeholder: "paste key — memory only, cleared on TTL/restart", autocomplete: "off" });
    const ttl = h("input", { type: "number", value: "3600", title: "TTL seconds" });
    const status = h("div", { class: "row" });
    const refresh = async () => {
      clear(status);
      try {
        const s = (await api.credStatus(provider.value)) as { source: string; fingerprint: string | null };
        status.append(pill(`source: ${s.source}`, s.source === "none" ? "muted" : "ok"), s.fingerprint ? pill(`fingerprint ${s.fingerprint}`, "info") : pill("no key", "muted"));
      } catch (e) { status.append(pill(errMsg(e), "bad")); }
    };
    provider.addEventListener("change", () => void refresh());
    box.append(
      h("p", { class: "muted" }, "Precedence: environment → admin store → ephemeral UI. The value is never logged, persisted or returned; only a fingerprint is shown."),
      h("div", { class: "row" }, provider, value, ttl),
      h("div", { class: "row" },
        h("button", { class: "primary", onClick: async () => {
          try { await api.setTestKey(provider.value, value.value, Number(ttl.value)); value.value = ""; toast("ephemeral key set", "ok"); await refresh(); } catch (e) { toast(errMsg(e), "bad"); }
        } }, "Set for this session"),
        h("button", { class: "danger", onClick: async () => {
          try { await api.clearTestKey(provider.value); toast("cleared", "ok"); await refresh(); } catch (e) { toast(errMsg(e), "bad"); }
        } }, "Clear"),
      ),
      status,
    );
    await refresh();
  };
  void draw();
  return card;
}

function registryCard(): HTMLElement {
  const box = h("div");
  const card = section("Capability registry (adapter self-declarations + platform facts)", box);
  card.classList.add("span2");
  void (async () => {
    try {
      const r = (await api.registry()) as { adapters: { adapter: string; role: string; capabilities: { name: string; state: string }[] }[] };
      for (const a of r.adapters) {
        box.append(h("h3", {}, `${a.role} / ${a.adapter}`), h("div", {}, ...a.capabilities.map((c) => pill(`${c.name}: ${c.state}`, toneFor(c.state)))));
      }
      box.append(h("details", {}, h("summary", {}, "raw"), pre(r)));
    } catch (e) { box.append(h("p", { class: "muted" }, errMsg(e))); }
  })();
  return card;
}
