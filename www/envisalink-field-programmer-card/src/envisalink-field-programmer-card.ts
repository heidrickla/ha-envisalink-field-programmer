import { LitElement, html, css, nothing, TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  FUNCTION_KEY_ACTIONS,
  HARDWIRE_TYPES,
  RESPONSE_TIMES,
  SYSTEM_TIMING_FIELDS,
  ZONE_TYPES,
  ZONE_TYPES_BY_CODE,
} from "./field-programming-data";

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

interface EnvisalinkFieldProgrammerCardConfig {
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

type ProgrammingTab = "zone" | "timing" | "keys" | "raw";

@customElement("envisalink-field-programmer-card")
export class EnvisalinkFieldProgrammerCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: EnvisalinkFieldProgrammerCardConfig;
  @state() private _showDisarmInput = false;
  @state() private _disarmCode = "";

  // Field-programming console: collapsed behind one explicit toggle, then
  // split into tabs. Only "raw" ever exposes bare keystrokes.
  @state() private _showFieldProgramming = false;
  @state() private _progTab: ProgrammingTab = "zone";
  @state() private _progError: string | null = null;
  @state() private _progBusy = false;

  // Zone-program form state.
  @state() private _zpZone = "1";
  @state() private _zpType = 3;
  @state() private _zpPartition = "1";
  @state() private _zpReportEnabled = true;
  @state() private _zpHardwireType = "0";
  @state() private _zpResponseTime = "1";
  @state() private _zpConfirm = false;
  @state() private _zpConfirmLifeSafety = false;

  // System-timing form state.
  @state() private _stField = SYSTEM_TIMING_FIELDS[0].field;
  @state() private _stValue = "60";
  @state() private _stConfirm = false;

  // Function-key form state.
  @state() private _fkKey = "A";
  @state() private _fkPartition = "1";
  @state() private _fkAction = 3;
  @state() private _fkConfirm = false;

  // Raw keystroke console (the original escape hatch).
  @state() private _rawPartition = "1";
  @state() private _rawKeys = "";
  @state() private _rawConfirm = false;

  setConfig(config: EnvisalinkFieldProgrammerCardConfig): void {
    if (!config.alarm_entity) {
      throw new Error("envisalink-field-programmer-card: `alarm_entity` is required");
    }
    this._config = { show_programming_console: true, ...config };
  }

  getCardSize(): number {
    return 6;
  }

  static getStubConfig(): Partial<EnvisalinkFieldProgrammerCardConfig> {
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
              <span>${this._config.title ?? "Security Console"}</span>
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

          ${this._config.show_programming_console
            ? this._renderFieldProgrammingSection()
            : nothing}

          ${zones.length
            ? html`<div class="zones">
                ${zones.map((z) => this._renderZone(z))}
              </div>`
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

  // -- Field programming: entry point + tab shell -------------------------

  private _renderFieldProgrammingSection(): TemplateResult {
    if (!this._showFieldProgramming) {
      return html`<button
        class="prog-toggle"
        @click=${() => (this._showFieldProgramming = true)}
      >
        <ha-icon icon="mdi:wrench-cog"></ha-icon>
        Field Programming
      </button>`;
    }

    const tabs: { id: ProgrammingTab; label: string }[] = [
      { id: "zone", label: "Zones" },
      { id: "timing", label: "Timing" },
      { id: "keys", label: "Function Keys" },
      { id: "raw", label: "Raw" },
    ];

    return html`<div class="programming">
      <div class="banner warning">
        <ha-icon icon="mdi:alert-octagon"></ha-icon>
        Every action here opens the panel's installer Program Mode. This
        integration cannot read back what's currently on the keypad display,
        so double-check at the physical keypad first if you're not sure
        what's already programmed -- especially for smoke/CO detector zones.
      </div>
      <div class="tabs">
        ${tabs.map(
          (t) => html`<button
            class="tab ${this._progTab === t.id ? "active" : ""}"
            @click=${() => {
              this._progTab = t.id;
              this._progError = null;
            }}
          >
            ${t.label}
          </button>`
        )}
      </div>
      ${this._progTab === "zone" ? this._renderZoneProgramForm() : nothing}
      ${this._progTab === "timing" ? this._renderSystemTimingForm() : nothing}
      ${this._progTab === "keys" ? this._renderFunctionKeyForm() : nothing}
      ${this._progTab === "raw" ? this._renderRawKeystrokeForm() : nothing}
      ${this._progError
        ? html`<div class="banner trouble">${this._progError}</div>`
        : nothing}
      <div class="actions">
        <button
          class="btn disarm"
          @click=${() => (this._showFieldProgramming = false)}
        >
          Close
        </button>
      </div>
    </div>`;
  }

  // -- Zone programming tab ------------------------------------------------

  private _renderZoneProgramForm(): TemplateResult {
    const zoneNum = Number(this._zpZone) || 1;
    const selected = ZONE_TYPES_BY_CODE[this._zpType];
    const isHardwiredZone = zoneNum <= 8;
    const showHardwireType = zoneNum >= 2 && zoneNum <= 8;

    return html`
      <div class="prog-row">
        <label>Zone #</label>
        <input
          class="prog-input small"
          type="number"
          min="1"
          max="64"
          .value=${this._zpZone}
          @input=${(e: InputEvent) => (this._zpZone = (e.target as HTMLInputElement).value)}
        />
        <label>Partition</label>
        <select
          class="prog-input small"
          .value=${this._zpPartition}
          @change=${(e: Event) =>
            (this._zpPartition = (e.target as HTMLSelectElement).value)}
        >
          ${[1, 2, 3].map((p) => html`<option value=${p}>${p}</option>`)}
        </select>
      </div>
      <div class="prog-row column">
        <label>Zone type</label>
        <select
          class="prog-input wide"
          .value=${String(this._zpType)}
          @change=${(e: Event) =>
            (this._zpType = Number((e.target as HTMLSelectElement).value))}
        >
          ${ZONE_TYPES.map(
            (zt) => html`<option value=${zt.code}>${zt.label}</option>`
          )}
        </select>
        ${selected
          ? html`<p class="field-help">${selected.description}</p>`
          : nothing}
      </div>
      ${selected?.lifeSafety
        ? html`<div class="banner trouble">
            <ha-icon icon="mdi:fire-alert"></ha-icon>
            This is a life-safety zone type (fire/CO). Getting this wrong on
            a real detector's zone can silence it. Requires an extra
            confirmation below.
          </div>`
        : nothing}
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._zpReportEnabled}
          @change=${(e: Event) =>
            (this._zpReportEnabled = (e.target as HTMLInputElement).checked)}
        />
        Report to monitoring station
      </label>
      ${showHardwireType
        ? html`<div class="prog-row column">
            <label>Hardwire type</label>
            <select
              class="prog-input wide"
              .value=${this._zpHardwireType}
              @change=${(e: Event) =>
                (this._zpHardwireType = (e.target as HTMLSelectElement).value)}
            >
              ${HARDWIRE_TYPES.map(
                (h) => html`<option value=${h.value}>${h.label}</option>`
              )}
            </select>
          </div>`
        : nothing}
      ${isHardwiredZone
        ? html`<div class="prog-row column">
            <label>Response time</label>
            <select
              class="prog-input wide"
              .value=${this._zpResponseTime}
              @change=${(e: Event) =>
                (this._zpResponseTime = (e.target as HTMLSelectElement).value)}
            >
              ${RESPONSE_TIMES.map(
                (r) => html`<option value=${r.value}>${r.label}</option>`
              )}
            </select>
          </div>`
        : html`<p class="field-help">
            Zone 9+: treated as an auxiliary-wired zone. Wireless (RF) sensor
            enrollment isn't supported here -- enroll the transmitter at the
            keypad first, then use this to set its type/partition.
          </p>`}
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._zpConfirm}
          @change=${(e: Event) =>
            (this._zpConfirm = (e.target as HTMLInputElement).checked)}
        />
        I understand this opens Program Mode on the panel.
      </label>
      ${selected?.lifeSafety
        ? html`<label class="confirm-row">
            <input
              type="checkbox"
              .checked=${this._zpConfirmLifeSafety}
              @change=${(e: Event) =>
                (this._zpConfirmLifeSafety = (e.target as HTMLInputElement).checked)}
            />
            I confirm this life-safety zone type change is intentional.
          </label>`
        : nothing}
      <div class="actions">
        <button class="btn away" ?disabled=${this._progBusy} @click=${() => this._submitZoneProgram()}>
          Apply
        </button>
      </div>
    `;
  }

  private async _submitZoneProgram(): Promise<void> {
    const entryId = this._entryId;
    this._progError = null;
    if (!entryId) {
      this._progError = "Could not determine the config entry id for this card.";
      return;
    }
    if (!this._zpConfirm) {
      this._progError = "Check the Program Mode confirmation box first.";
      return;
    }
    this._progBusy = true;
    try {
      await this.hass.callService("envisalink_field_programmer", "program_zone", {
        entry_id: entryId,
        zone_number: Number(this._zpZone),
        zone_type: this._zpType,
        partition: Number(this._zpPartition),
        report_enabled: this._zpReportEnabled,
        hardwire_type: this._zpHardwireType,
        response_time: this._zpResponseTime,
        confirm: this._zpConfirm,
        confirm_life_safety: this._zpConfirmLifeSafety,
      });
    } catch (err) {
      this._progError = err instanceof Error ? err.message : String(err);
    } finally {
      this._progBusy = false;
    }
  }

  // -- System timing tab ---------------------------------------------------

  private _renderSystemTimingForm(): TemplateResult {
    const info = SYSTEM_TIMING_FIELDS.find((f) => f.field === this._stField)!;
    return html`
      <div class="prog-row column">
        <label>Field</label>
        <select
          class="prog-input wide"
          .value=${this._stField}
          @change=${(e: Event) => {
            this._stField = (e.target as HTMLSelectElement).value;
            this._stValue = String(
              SYSTEM_TIMING_FIELDS.find((f) => f.field === this._stField)!.min
            );
          }}
        >
          ${SYSTEM_TIMING_FIELDS.map(
            (f) => html`<option value=${f.field}>${f.label}</option>`
          )}
        </select>
        <p class="field-help">${info.description}</p>
      </div>
      <div class="prog-row">
        <label>Value</label>
        <input
          class="prog-input small"
          type="number"
          min="0"
          max="240"
          .value=${this._stValue}
          @input=${(e: InputEvent) => (this._stValue = (e.target as HTMLInputElement).value)}
        />
        ${Object.keys(info.specials).length
          ? html`<span class="field-help inline">
              (${Object.entries(info.specials)
                .map(([k, v]) => `${k}=${v}`)
                .join(", ")})
            </span>`
          : nothing}
      </div>
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._stConfirm}
          @change=${(e: Event) =>
            (this._stConfirm = (e.target as HTMLInputElement).checked)}
        />
        I understand this opens Program Mode on the panel.
      </label>
      <div class="actions">
        <button class="btn away" ?disabled=${this._progBusy} @click=${() => this._submitSystemTiming()}>
          Apply
        </button>
      </div>
    `;
  }

  private async _submitSystemTiming(): Promise<void> {
    const entryId = this._entryId;
    this._progError = null;
    if (!entryId) {
      this._progError = "Could not determine the config entry id for this card.";
      return;
    }
    if (!this._stConfirm) {
      this._progError = "Check the Program Mode confirmation box first.";
      return;
    }
    this._progBusy = true;
    try {
      await this.hass.callService("envisalink_field_programmer", "set_system_timing", {
        entry_id: entryId,
        field: this._stField,
        value: Number(this._stValue),
        confirm: this._stConfirm,
      });
    } catch (err) {
      this._progError = err instanceof Error ? err.message : String(err);
    } finally {
      this._progBusy = false;
    }
  }

  // -- Function keys tab ----------------------------------------------------

  private _renderFunctionKeyForm(): TemplateResult {
    return html`
      <div class="prog-row">
        <label>Key</label>
        <select
          class="prog-input small"
          .value=${this._fkKey}
          @change=${(e: Event) => (this._fkKey = (e.target as HTMLSelectElement).value)}
        >
          ${["A", "B", "C", "D"].map((k) => html`<option value=${k}>${k}</option>`)}
        </select>
        <label>Partition</label>
        <select
          class="prog-input small"
          .value=${this._fkPartition}
          @change=${(e: Event) =>
            (this._fkPartition = (e.target as HTMLSelectElement).value)}
        >
          ${[1, 2, 3].map((p) => html`<option value=${p}>${p}</option>`)}
        </select>
      </div>
      <div class="prog-row column">
        <label>Action</label>
        <select
          class="prog-input wide"
          .value=${String(this._fkAction)}
          @change=${(e: Event) =>
            (this._fkAction = Number((e.target as HTMLSelectElement).value))}
        >
          ${FUNCTION_KEY_ACTIONS.map(
            (a) => html`<option value=${a.value}>${a.label}</option>`
          )}
        </select>
      </div>
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._fkConfirm}
          @change=${(e: Event) =>
            (this._fkConfirm = (e.target as HTMLInputElement).checked)}
        />
        I understand this opens Program Mode on the panel.
      </label>
      <div class="actions">
        <button class="btn away" ?disabled=${this._progBusy} @click=${() => this._submitFunctionKey()}>
          Apply
        </button>
      </div>
    `;
  }

  private async _submitFunctionKey(): Promise<void> {
    const entryId = this._entryId;
    this._progError = null;
    if (!entryId) {
      this._progError = "Could not determine the config entry id for this card.";
      return;
    }
    if (!this._fkConfirm) {
      this._progError = "Check the Program Mode confirmation box first.";
      return;
    }
    this._progBusy = true;
    try {
      await this.hass.callService("envisalink_field_programmer", "program_function_key", {
        entry_id: entryId,
        key: this._fkKey,
        partition: Number(this._fkPartition),
        action: this._fkAction,
        confirm: this._fkConfirm,
      });
    } catch (err) {
      this._progError = err instanceof Error ? err.message : String(err);
    } finally {
      this._progBusy = false;
    }
  }

  // -- Raw keystroke tab (escape hatch for anything the guided forms above
  // don't cover) ------------------------------------------------------------

  private _renderRawKeystrokeForm(): TemplateResult {
    return html`
      <p class="field-help">
        For anything the guided tabs above don't cover. Sequences that open
        Program Mode (installer code followed by 800) need the confirmation
        box below.
      </p>
      <div class="prog-row">
        <label>Partition</label>
        <input
          class="prog-input small"
          type="number"
          min="1"
          max="8"
          .value=${this._rawPartition}
          @input=${(e: InputEvent) =>
            (this._rawPartition = (e.target as HTMLInputElement).value)}
        />
      </div>
      <div class="prog-row">
        <label>Keys</label>
        <input
          class="prog-input"
          type="text"
          placeholder="e.g. *101#"
          .value=${this._rawKeys}
          @input=${(e: InputEvent) => (this._rawKeys = (e.target as HTMLInputElement).value)}
        />
      </div>
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._rawConfirm}
          @change=${(e: Event) =>
            (this._rawConfirm = (e.target as HTMLInputElement).checked)}
        />
        I understand the Program Mode / fire-safety risk above.
      </label>
      <div class="actions">
        <button class="btn away" ?disabled=${this._progBusy} @click=${() => this._sendRawKeystrokes()}>
          Send
        </button>
      </div>
    `;
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
    await this.hass.callService("envisalink_field_programmer", "toggle_zone_bypass", {
      entry_id: entryId,
      zone: zone.attributes.zone_number,
    });
  }

  private async _sendRawKeystrokes(): Promise<void> {
    const entryId = this._entryId;
    this._progError = null;
    if (!entryId) {
      this._progError = "Could not determine the config entry id for this card.";
      return;
    }
    if (!this._rawKeys.trim()) {
      this._progError = "Enter a keystroke sequence first.";
      return;
    }
    this._progBusy = true;
    try {
      await this.hass.callService("envisalink_field_programmer", "send_keystrokes", {
        entry_id: entryId,
        partition: Number(this._rawPartition) || 1,
        keys: this._rawKeys,
        confirm_installer_risk: this._rawConfirm,
      });
      this._rawKeys = "";
    } catch (err) {
      this._progError = err instanceof Error ? err.message : String(err);
    } finally {
      this._progBusy = false;
    }
  }

  static styles = css`
    :host {
      --vc-bg: #0f172a;
      --vc-bg-raised: #1e293b;
      --vc-border: #334155;
      --vc-text: #e2e8f0;
      --vc-text-dim: #94a3b8;
      /* Accent hues are loosely inspired by the Envisalink/EyezOn bridge
         this card talks to (their site uses a crimson/violet/amber accent
         trio over a dark charcoal base) -- a nod for visual harmony, not a
         reproduction of their branding. Falls back to the light/dark HA
         theme's own tone where it matters (borders, surfaces, text) so this
         only touches the armed-state accent colors, not the whole theme. */
      --vc-away: #e11d48;
      --vc-home: #7c3aed;
      --vc-night: #d97706;
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
      background: rgba(217, 119, 6, 0.12);
      color: #fcd34d;
      border: 1px solid rgba(217, 119, 6, 0.35);
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
      color: var(--vc-night);
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
      color: white;
      transition: transform 0.1s ease;
    }
    .btn:active {
      transform: scale(0.96);
    }
    .btn:disabled {
      opacity: 0.5;
      cursor: default;
    }
    .btn.away { background: var(--vc-away); }
    .btn.home { background: var(--vc-home); }
    .btn.night { background: var(--vc-night); color: #1c1917; }
    .btn.disarm { background: var(--vc-safe); color: #0f172a; }
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
    .prog-input.wide {
      width: 100%;
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
      color: var(--vc-night);
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
      background: var(--vc-night);
      color: #1c1917;
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
      margin-bottom: 14px;
    }
    .programming {
      border: 1px solid var(--vc-border);
      border-radius: 12px;
      padding: 12px;
      background: rgba(0, 0, 0, 0.15);
      margin-bottom: 14px;
    }
    .tabs {
      display: flex;
      gap: 4px;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--vc-border);
    }
    .tab {
      background: transparent;
      border: none;
      color: var(--vc-text-dim);
      padding: 8px 10px;
      font-size: 0.82rem;
      cursor: pointer;
      border-bottom: 2px solid transparent;
    }
    .tab.active {
      color: var(--vc-text);
      border-bottom-color: var(--vc-home);
    }
    .prog-row {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .prog-row.column {
      flex-direction: column;
      align-items: stretch;
    }
    .prog-row label {
      min-width: 70px;
      font-size: 0.85rem;
      color: var(--vc-text-dim);
    }
    .field-help {
      font-size: 0.78rem;
      color: var(--vc-text-dim);
      margin: 4px 0 0;
      line-height: 1.4;
    }
    .field-help.inline {
      margin: 0;
      white-space: nowrap;
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
    "envisalink-field-programmer-card": EnvisalinkFieldProgrammerCard;
  }
}

(window as any).customCards = (window as any).customCards || [];
(window as any).customCards.push({
  type: "envisalink-field-programmer-card",
  name: "Envisalink Field Programmer Card",
  description: "Modern control + guided field-programming console for an alarm panel bridged via Envisalink.",
});
