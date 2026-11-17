// SubGuard: small site-wide JavaScript helpers.
// Bootstrap's JS (window.bootstrap) is loaded before this file in base.html.

document.addEventListener("DOMContentLoaded", () => {
  setUpConfirmDialogs();
  setUpFilterPills();
  setUpTrialOnlyFields();
  setUpAutoSubmitForms();

  // Turn on Bootstrap tooltips (elements with data-bs-toggle="tooltip").
  document
    .querySelectorAll('[data-bs-toggle="tooltip"]')
    .forEach((el) => new bootstrap.Tooltip(el));
});

/**
 * Confirmation dialogs.
 * Any <form data-confirm="Message"> shows the shared modal before submitting.
 * Optional: data-confirm-button="Delete" changes the button text.
 * Forms with data-demo only show a notice (used on preview pages).
 */
function setUpConfirmDialogs() {
  const modalEl = document.getElementById("confirmModal");
  if (!modalEl) return;

  const modal = new bootstrap.Modal(modalEl);
  const body = document.getElementById("confirmModalBody");
  const okButton = document.getElementById("confirmModalOk");
  let pendingForm = null;

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.dataset.confirmed === "true") return; // already confirmed: let it submit
      event.preventDefault();
      pendingForm = form;
      body.textContent = form.dataset.confirm;
      okButton.textContent = form.dataset.confirmButton || "Confirm";
      modal.show();
    });
  });

  okButton.addEventListener("click", () => {
    if (!pendingForm) return;
    modal.hide();
    if (pendingForm.hasAttribute("data-demo")) {
      showToast("This is sample data. Manage saved subscriptions on the Subscriptions page.");
      pendingForm = null;
      return;
    }
    pendingForm.dataset.confirmed = "true";
    pendingForm.requestSubmit();
  });
}

/**
 * Filter pills: buttons inside [data-filter-group] show/hide
 * the elements marked [data-filter-item] whose data-status matches.
 */
function setUpFilterPills() {
  document.querySelectorAll("[data-filter-group]").forEach((group) => {
    const target = document.querySelector(group.dataset.filterGroup);
    if (!target) return;
    const buttons = group.querySelectorAll("[data-filter]");

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const value = button.dataset.filter;
        buttons.forEach((b) => {
          const isActive = b === button;
          b.classList.toggle("active", isActive);
          b.setAttribute("aria-pressed", String(isActive));
        });
        target.querySelectorAll("[data-filter-item]").forEach((item) => {
          item.hidden = value !== "all" && item.dataset.status !== value;
        });
      });
    });
  });
}

/**
 * Trial-only fields: <div data-trial-only="#typeSelectId"> is hidden
 * while the subscription type is "paid". The server ignores the value
 * for paid subscriptions either way.
 */
function setUpTrialOnlyFields() {
  document.querySelectorAll("[data-trial-only]").forEach((wrapper) => {
    const typeSelect = document.querySelector(wrapper.dataset.trialOnly);
    if (!typeSelect) return;
    const update = () => {
      wrapper.hidden = typeSelect.value === "paid";
    };
    typeSelect.addEventListener("change", update);
    update();
  });
}

/**
 * <form data-auto-submit> submits as soon as one of its dropdowns changes,
 * so filters apply without pressing the button. The button still works
 * for the search box and when JavaScript is off.
 */
function setUpAutoSubmitForms() {
  document.querySelectorAll("form[data-auto-submit]").forEach((form) => {
    form.querySelectorAll("select").forEach((select) => {
      select.addEventListener("change", () => form.requestSubmit());
    });
  });
}

/** Show a small notification in the bottom-right corner. */
function showToast(message) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast align-items-center text-bg-dark border-0";
  toast.setAttribute("role", "status");
  toast.innerHTML =
    '<div class="d-flex"><div class="toast-body"></div>' +
    '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>';
  toast.querySelector(".toast-body").textContent = message;
  container.appendChild(toast);
  toast.addEventListener("hidden.bs.toast", () => toast.remove());
  new bootstrap.Toast(toast).show();
}
