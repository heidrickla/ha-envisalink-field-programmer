import { LitElement, html, css, nothing, TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

interface HassEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, any>;
}

interface HomeAssistant {
  states: Record<string, HassEntity>;
  callService: (
    domain: string,
    service: string,
    data?: Record<string, unknown>
  ) => Promise<unknown>;
}

interface VistaConsoleCardConfig {
  type: string;
  title?: string;
  alarm_entity: string;
  zone_entities?: string[];
  entry_id?: string;
  show_programming_console?: boolean;
}

const ARM_STATE_LABELS: Record<string, string> = {
  disarmed: "Disarmed",
  armed_away: "Armed · Away",
  armed_home: "Armed · Home",
  armed_night: "Armed · Night",
  arming: "Arming…",
  pending: "Entry Delay…",
  triggered: "ALARM",
  unavailable: "Unavailable",
  unknown: "Unknown",
};

@customElement("vista-console-card")
export class VistaConsoleCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: VistaConsoleCardConfig;
  @state() private _showProgramming = false;
  @state() private _showDisarmInput = false;
  @state() private _disarmCode = "";
  @state() private _progPartition = "1";
  @state() private _progKeys = "";
  @state() private _progConfirm = false;
  @state() private _progError: string | null = null;

  setConfig(config: VistaConsoleCardConfig): void {
    if (!config.alarm_entity) {
      throw new Error("vista-console-card: `alarm_entity` is required");
    }
    this._config = { show_programming_console: true, ...config };
  }

  getCardSize(): number {
    return 6;
  }

  static getStubConfig(): Partial<VistaConsoleCardConfig> {
    return { alarm_entity: "alarm_control_panel.partition" };
  }

  private get _entryId(): string | undefined {
    const alarm = this.hass?.states[this._config.alarm_entity];
    return this._config.entry_id ?? alarm?.attributes?.config_entry_id;
  }

  private _zoneEntities(): HassEntity[] {
    if (!this.hass) return [];
    if (this._config.zone_entities?.length) {
      return this._config.zone_entities
        .map((id) => this.hass.states[id])
        .filter((e): e is HassEntity => !!e);
    }
    const entryId = this._entryId;
    return Object.values(this.hass.states).filter(
      (e) =>
        e.entity_id.startsWith("binary_sensor.") &&
        e.attributes.config_entry_id === entryId &&
        e.attributes.zone_number !== undefined
    );
  }

  private _troubleEntity(): HassEntity | undefined {
    const entryId = this._entryId;
    return Object.values(this.hass.states).find(
      (e) =>
        e.entity_id.startsWith("binary_sensor.") &&
        e.attributes.config_entry_id === entryId &&
        e.attributes.zone_number === undefined
    );
  }

  render(): TemplateResult {
    if (!this.hass || !this._config) return html``;
    const alarm = this.hass.states[this._config.alarm_entity];
    if (!alarm) {
      return html`<ha-card>
        <div class="warning">Entity ${this._config.alarm_entity} not found.</div>
      </ha-card>`;
    }

    const armState = alarm.state in ARM_STATE_LABELS ? alarm.state : "unknown";
    const trouble = this._troubleEntity();
    const zones = this._zoneEntities().sort(
      (a, b) => (a.attributes.zone_number ?? 0) - (b.attributes.zone_number ?? 0)
    );

    return html`
      <ha-card>
        <div class="console state-${armState}">
          <div class="header">
            <div class="title">
              <ha-icon icon="mdi:shield-home"></ha-icon>
              <span>${this._config.title ?? "Vista Console"}</span>
            </div>
            <div class="conn-dot ${alarm.state === "unavailable" ? "off" : "on"}"></div>
          </div>

          ${trouble?.state === "on"
            ? html`<div class="banner trouble">
                <ha-icon icon="mdi:alert"></ha-icon>
                System trouble condition present
              </div>`
            : nothing}

          <div class="status-block">
            <div class="status-label">${ARM_STATE_LABELS[armState]}</div>
            ${this._renderActions(armState)}
          </div>

          ${zones.length
            ? html`<div class="zones">
                ${zones.map((z) => this._renderZone(z))}
              </div>`
            : nothing}

          ${this._config.show_programming_console
            ? this._renderProgrammingConsole()
            : nothing}
        </div>
      </ha-card>
    `;
  }

  private _renderActions(armState: string): TemplateResult {
    if (armState === "disarmed") {
      return html`<div class="actions">
        <button class="btn away" @click=${() => this._arm("away")}>Away</button>
        <button class="btn home" @click=${() => this._arm("home")}>Home</button>
        <button class="btn night" @click=${() => this._arm("night")}>Night</button>
      </div>`;
    }
    return html`<div class="actions">
      ${this._showDisarmInput
        ? html`<input
              class="code-input"
              type="password"
              inputmode="numeric"
              placeholder="Code"
              .value=${this._disarmCode}
              @input=${(e: InputEvent) =>
                (this._disarmCode = (e.target as HTMLInputElement).value)}
            />
            <button class="btn disarm" @click=${() => this._disarm()}>Confirm</button>`
        : html`<button
            class="btn disarm"
            @click=${() => (this._showDisarmInput = true)}
          >
            Disarm
          </button>`}
    </div>`;
  }

  private _renderZone(zone: HassEntity): TemplateResult {
    const open = zone.state === "on";
    const bypassed = !!zone.attributes.bypassed;
    const fault = !!zone.attributes.fault;
    const tamper = !!zone.attributes.tamper;
    const name = zone.attributes.friendly_name ?? zone.entity_id;
    return html`<div
      class="zone ${open ? "open" : "closed"} ${bypassed ? "bypassed" : ""} ${
      fault || tamper ? "fault" : ""
    }"
      title=${name}
      @click=${() => this._toggleBypass(zone)}
    >
      <ha-icon icon=${open ? "mdi:door-open" : "mdi:door-closed"}></ha-icon>
      <span class="zone-name">${name}</span>
      ${bypassed ? html`<span class="pill">BYPASS</span>` : nothing}
    </div>`;
  }

  private _renderProgrammingConsole(): TemplateResult {
    if (!this._showProgramming) {
      return html`<button
        class="prog-toggle"
        @click=${() => (this._showProgramming = true)}
      >
        <ha-icon icon="mdi:wrench-cog"></ha-icon>
        Advanced Programming Console
      </button>`;
    }
    return html`<div class="programming">
      <div class="banner warning">
        <ha-icon icon="mdi:alert-octagon"></ha-icon>
        Raw keypad sequences. A sequence containing <code>*8</code> enters
        installer programming and can lock the panel out until it is
        power-cycled; installer mode also governs fire-zone and
        UL-listing-relevant settings. Only proceed if you know exactly what
        this sequence does on a Vista panel.
      </div>
      <div class="prog-row">
        <label>Partition</label>
        <input
          class="prog-input small"
          type="number"
          min="1"
          max="8"
          .value=${this._progPartition}
          @input=${(e: InputEvent) =>
            (this._progPartition = (e.target as HTMLInputElement).value)}
        />
      </div>
      <div class="prog-row">
        <label>Keys</label>
        <input
          class="prog-input"
          type="text"
          placeholder="e.g. *1 01 #"
          .value=${this._progKeys}
          @input=${(e: InputEvent) =>
            (this._progKeys = (e.target as HTMLInputElement).value)}
        />
      </div>
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._progConfirm}
          @change=${(e: Event) =>
            (this._progConfirm = (e.target as HTMLInputElement).checked)}
        />
        I understand the installer-mode / fire-safety risk above.
      </label>
      ${this._progError
        ? html`<div class="banner trouble">${this._progError}</div>`
        : nothing}
      <div class="actions">
        <button class="btn away" @click=${() => this._sendKeystrokes()}>
          Send
        </button>
        <button
          class="btn disarm"
          @click=${() => (this._showProgramming = false)}
        >
          Close
        </button>
      </div>
    </div>`;
  }

  private async _arm(mode: "away" | "home" | "night"): Promise<void> {
    await this.hass.callService("alarm_control_panel", `alarm_arm_${mode}`, {
      entity_id: this._config.alarm_entity,
    });
  }

  private async _disarm(): Promise<void> {
    await this.hass.callService("alarm_control_panel", "alarm_disarm", {
      entity_id: this._config.alarm_entity,
      code: this._disarmCode || undefined,
    });
    this._disarmCode = "";
    this._showDisarmInput = false;
  }

  private async _toggleBypass(zone: HassEntity): Promise<void> {
    const entryId = this._entryId;
    if (!entryId) return;
    const name = zone.attributes.friendly_name ?? zone.entity_id;
    const action = zone.attributes.bypassed ? "un-bypass" : "bypass";
    if (!window.confirm(`${action === "bypass" ? "Bypass" : "Un-bypass"} ${name}?`)) {
      return;
    }
    await this.hass.callService("vista_console", "toggle_zone_bypass", {
      entry_id: entryId,
      zone: zone.attributes.zone_number,
    });
  }

  private async _sendKeystrokes(): Promise<void> {
    const entryId = this._entryId;
    this._progError = null;
    if (!entryId) {
      this._progError = "Could not determine the config entry id for this card.";
      return;
    }
    if (!this._progKeys.trim()) {
      this._progError = "Enter a keystroke sequence first.";
      return;
    }
    if (this._progKeys.includes("*8") && !this._progConfirm) {
      this._progError =
        "This sequence enters installer mode. Check the confirmation box first.";
      return;
    }
    try {
      await this.hass.callService("vista_console", "send_keystrokes", {
        entry_id: entryId,
        partition: Number(this._progPartition) || 1,
        keys: this._progKeys,
        confirm_installer_risk: this._progConfirm,
      });
      this._progKeys = "";
    } catch (err) {
      this._progError = err instanceof Error ? err.message : String(err);
    }
  }

  static styles = css`
    :host {
      --vc-bg: #0f172a;
      --vc-bg-raised: #1e293b;
      --vc-border: #334155;
      --vc-text: #e2e8f0;
      --vc-text-dim: #94a3b8;
      --vc-away: #f59e0b;
      --vc-home: #3b82f6;
      --vc-night: #6366f1;
      --vc-safe: #22c55e;
      --vc-danger: #ef4444;
    }
    ha-card {
      overflow: hidden;
      border-radius: 16px;
    }
    .console {
      background: linear-gradient(160deg, var(--vc-bg), var(--vc-bg-raised));
      color: var(--vc-text);
      padding: 16px 18px 20px;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 1.05rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .conn-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .conn-dot.on {
      background: var(--vc-safe);
      box-shadow: 0 0 8px var(--vc-safe);
    }
    .conn-dot.off {
      background: var(--vc-danger);
    }
    .banner {
      display: flex;
      gap: 8px;
      align-items: flex-start;
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 0.85rem;
      margin-bottom: 12px;
      line-height: 1.4;
    }
    .banner.trouble {
      background: rgba(239, 68, 68, 0.15);
      color: #fca5a5;
      border: 1px solid rgba(239, 68, 68, 0.35);
    }
    .banner.warning {
      background: rgba(245, 158, 11, 0.12);
      color: #fcd34d;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .status-block {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--vc-border);
      border-radius: 12px;
      padding: 16px;
      text-align: center;
      margin-bottom: 14px;
    }
    .status-label {
      font-size: 1.4rem;
      font-weight: 700;
      margin-bottom: 12px;
      letter-spacing: 0.01em;
    }
    .state-armed_away .status-label {
      color: var(--vc-away);
    }
    .state-armed_home .status-label {
      color: var(--vc-home);
    }
    .state-armed_night .status-label {
      color: var(--vc-night);
    }
    .state-disarmed .status-label {
      color: var(--vc-safe);
    }
    .state-triggered .status-label {
      color: var(--vc-danger);
      animation: pulse 1s infinite;
    }
    .state-pending .status-label,
    .state-arming .status-label {
      color: var(--vc-away);
      animation: pulse 1.4s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    .actions {
      display: flex;
      gap: 8px;
      justify-content: center;
      flex-wrap: wrap;
    }
    .btn {
      border: none;
      border-radius: 8px;
      padding: 10px 16px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      color: #0f172a;
      transition: transform 0.1s ease;
    }
    .btn:active {
      transform: scale(0.96);
    }
    .btn.away { background: var(--vc-away); }
    .btn.home { background: var(--vc-home); color: white; }
    .btn.night { background: var(--vc-night); color: white; }
    .btn.disarm { background: var(--vc-safe); }
    .code-input, .prog-input {
      background: var(--vc-bg);
      border: 1px solid var(--vc-border);
      color: var(--vc-text);
      border-radius: 8px;
      padding: 9px 10px;
      font-size: 0.9rem;
    }
    .prog-input.small {
      width: 60px;
    }
    .zones {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }
    .zone {
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--vc-border);
      border-radius: 10px;
      padding: 8px 10px;
      cursor: pointer;
      font-size: 0.82rem;
      transition: border-color 0.15s ease;
    }
    .zone:hover {
      border-color: var(--vc-home);
    }
    .zone.open {
      color: var(--vc-away);
    }
    .zone.closed {
      color: var(--vc-text-dim);
    }
    .zone.fault {
      border-color: var(--vc-danger);
      color: var(--vc-danger);
    }
    .zone-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pill {
      margin-left: auto;
      background: var(--vc-away);
      color: #0f172a;
      font-size: 0.65rem;
      font-weight: 700;
      border-radius: 6px;
      padding: 2px 5px;
    }
    .prog-toggle {
      width: 100%;
      background: transparent;
      border: 1px dashed var(--vc-border);
      color: var(--vc-text-dim);
      border-radius: 10px;
      padding: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      cursor: pointer;
      font-size: 0.85rem;
    }
    .programming {
      border: 1px solid var(--vc-border);
      border-radius: 12px;
      padding: 12px;
      background: rgba(0, 0, 0, 0.15);
    }
    .prog-row {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .prog-row label {
      width: 70px;
      font-size: 0.85rem;
      color: var(--vc-text-dim);
    }
    .confirm-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
      color: var(--vc-text-dim);
      margin-bottom: 10px;
    }
    .warning {
      padding: 16px;
      color: var(--vc-danger);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "vista-console-card": VistaConsoleCard;
  }
}

(window as any).customCards = (window as any).customCards || [];
(window as any).customCards.push({
  type: "vista-console-card",
  name: "Vista Console Card",
  description: "Modern control + programming console for a Vista panel bridged via Envisalink.",
});
