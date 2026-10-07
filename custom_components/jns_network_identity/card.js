class JnsNetworkBindingsCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 4; }

  _render() {
    if (!this._hass) return;
    const entity = this._hass.states["sensor.jns_network_identity_status"];
    const state = entity ? entity.state : "ready";
    const a = entity ? entity.attributes : {};
    this.innerHTML = `
      <ha-card header="Network Infrastructure · DHCP/DNS Identity Import">
        <div style="padding:16px">
          <p style="margin-top:0">
            Upload the DrayTek DHCP/MAC binding text export. Only 10.10.10.150–187 is processed.
            DNS identities are derived from the final six MAC digits as <b>JNS-######</b>.
          </p>
          <input id="jns-file" type="file" accept=".txt,.cfg,.csv,text/plain" />
          <mwc-button id="jns-import" raised style="margin-left:8px">Upload &amp; update DNS</mwc-button>
          <div id="jns-live" style="margin-top:14px;font-weight:500"></div>
          <div style="margin-top:14px">
            <div><b>Status:</b> ${state}</div>
            <div><b>Last run:</b> ${a.last_run || "Never"}</div>
            <div><b>Bindings parsed:</b> ${a.parsed ?? 0}</div>
            <div><b>DNS changed:</b> ${a.changed ?? 0}</div>
            <div><b>Already correct:</b> ${a.unchanged ?? 0}</div>
            <div><b>Ignored:</b> ${a.ignored ?? 0}</div>
          </div>
        </div>
      </ha-card>`;

    const button = this.querySelector("#jns-import");
    if (button) button.onclick = () => this._upload();
  }

  async _upload() {
    const input = this.querySelector("#jns-file");
    const live = this.querySelector("#jns-live");
    if (!input?.files?.length) {
      live.textContent = "Choose the DrayTek binding file first.";
      return;
    }
    const file = input.files[0];
    if (file.size > 2 * 1024 * 1024) {
      live.textContent = "Rejected: file is larger than 2 MB.";
      return;
    }

    try {
      live.textContent = "Uploading…";
      const fd = new FormData();
      fd.append("file", file);
      const response = await this._hass.fetchWithAuth("/api/file_upload", {
        method: "POST",
        body: fd,
      });
      if (!response.ok) throw new Error("Upload failed");
      const uploaded = await response.json();

      live.textContent = "Validating bindings and updating DNS-A…";
      await this._hass.callService(
        "jns_network_identity",
        "import_bindings",
        { file_id: uploaded.file_id }
      );
      live.textContent = "Import completed. Status updated below.";
      setTimeout(() => this._render(), 800);
    } catch (err) {
      live.textContent = "Import failed: " + (err?.message || String(err));
    }
  }
}

if (!customElements.get("jns-network-bindings-card")) {
  customElements.define("jns-network-bindings-card", JnsNetworkBindingsCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "jns-network-bindings-card",
  name: "JNS Network Bindings Import",
  description: "Upload DrayTek DHCP/MAC bindings and maintain deterministic JNS DNS identities."
});
