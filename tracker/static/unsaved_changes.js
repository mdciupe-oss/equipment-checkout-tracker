// Warn before leaving a page with unsaved form changes.
// Usage: <form data-unsaved-guard> ; add data-start-dirty when the form was
// re-shown after a rejected save (its values are on screen but not stored).
(function () {
  document.querySelectorAll("form[data-unsaved-guard]").forEach(function (form) {
    function snapshot() {
      return new URLSearchParams(new FormData(form)).toString();
    }

    var initial = snapshot();
    var submitting = false;

    function isDirty() {
      return form.hasAttribute("data-start-dirty") || snapshot() !== initial;
    }

    form.addEventListener("submit", function () {
      submitting = true;
    });

    window.addEventListener("beforeunload", function (event) {
      if (!submitting && isDirty()) {
        event.preventDefault();
        event.returnValue = ""; // required by some browsers to show the dialog
      }
    });
  });
})();
