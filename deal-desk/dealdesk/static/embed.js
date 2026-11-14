/*
 * Deal Desk embed. One line on any page (for example a One Click Trade Action Plan step):
 *
 *   <div id="deal-desk"></div>
 *   <script src="https://<deal-desk-host>/embed.js" data-target="#deal-desk"
 *           data-destination="Germany" data-product="Olive oil" data-value="48000" data-currency="EUR"></script>
 *
 * The finished deal pack comes back as a DOM event on the target:
 *   document.querySelector('#deal-desk').addEventListener('dealdesk:complete', (e) => save(e.detail));
 * The host can also prefill later:  DealDesk.prefill({ destination: 'Kenya', mode: 'air' });
 */
(function () {
  var script = document.currentScript;
  if (!script) return;
  var origin = new URL(script.src).origin;
  var target = document.querySelector(script.dataset.target || "#deal-desk");
  if (!target) { target = document.createElement("div"); script.parentNode.insertBefore(target, script); }

  var params = new URLSearchParams({ embed: "1" });
  ["product", "origin", "destination", "value", "currency", "mode", "buyer"].forEach(function (k) {
    if (script.dataset[k]) params.set(k, script.dataset[k]);
  });

  var frame = document.createElement("iframe");
  frame.src = origin + "/?" + params.toString();
  frame.title = "Deal Desk: plan an export deal";
  frame.loading = "lazy";
  frame.style.cssText = "width:100%;border:0;min-height:640px;display:block";
  target.appendChild(frame);

  window.addEventListener("message", function (e) {
    if (e.origin !== origin || e.source !== frame.contentWindow) return;
    var m = e.data || {};
    if (m.type === "dealdesk:height" && m.height) frame.style.height = Math.max(640, m.height) + "px";
    if (m.type === "dealdesk:complete") {
      target.dispatchEvent(new CustomEvent("dealdesk:complete", { detail: m.pack, bubbles: true }));
    }
  });

  window.DealDesk = {
    prefill: function (deal) { frame.contentWindow.postMessage({ type: "dealdesk:prefill", deal: deal }, origin); },
  };
})();
