/* Group admin navigation links (parent / cyclist group select). */
(function () {
  function patternFromSelect(select) {
    return select.getAttribute("data-mcc-group-url-pattern");
  }

  function labelFromSelect(select) {
    return (
      select.getAttribute("data-mcc-group-link-label") || "Gruppe öffnen →"
    );
  }

  function navLinkForSelect(select) {
    var inline = select.closest(".mcc-group-nav-inline");
    if (inline) {
      var inInline = inline.querySelector("a.cyclist-group-admin-link");
      if (inInline) {
        return inInline;
      }
    }
    var linkId = select.getAttribute("data-mcc-nav-link-id");
    if (linkId) {
      var byId = document.getElementById(linkId);
      if (byId) {
        return byId;
      }
    }
    var link = document.createElement("a");
    link.className = "cyclist-group-admin-link";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    if (linkId) {
      link.id = linkId;
    }
    var host = inline || select.closest(".related-widget-wrapper") || select.parentElement;
    if (host) {
      host.appendChild(link);
    }
    return link;
  }

  function refresh(select) {
    var pattern = patternFromSelect(select);
    if (!pattern) {
      return;
    }
    var link = navLinkForSelect(select);
    if (!link) {
      return;
    }
    link.textContent = labelFromSelect(select);
    var id = select.value;
    if (id) {
      link.href = pattern.replace("{id}", id);
      link.style.display = "";
    } else {
      link.href = "#";
      link.style.display = "none";
    }
  }

  function bindSelect(select) {
    if (!select || select.dataset.mccGroupLinkBound === "1") {
      return;
    }
    if (!patternFromSelect(select)) {
      return;
    }
    select.dataset.mccGroupLinkBound = "1";
    select.addEventListener("change", function () {
      refresh(select);
    });
    refresh(select);
  }

  function discover() {
    var selects = document.querySelectorAll("select[data-mcc-group-url-pattern]");
    selects.forEach(bindSelect);
    var idParent = document.getElementById("id_parent");
    if (idParent) {
      bindSelect(idParent);
    }
    var idGroup = document.getElementById("id_group");
    if (idGroup) {
      bindSelect(idGroup);
    }
  }

  function boot() {
    discover();
    window.setTimeout(discover, 100);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  if (typeof django !== "undefined" && django.jQuery) {
    django.jQuery(document).on(
      "select2:select select2:clear",
      "select.admin-autocomplete",
      function () {
        bindSelect(this);
        refresh(this);
      }
    );
    django.jQuery(document).on("formset:added", function (event, $row, formsetName) {
      if (
        formsetName &&
        (formsetName.indexOf("grouptravelstatus") !== -1 ||
          formsetName.indexOf("groupeventstatus") !== -1 ||
          formsetName.indexOf("group_statuses") !== -1)
      ) {
        window.setTimeout(discover, 100);
      }
    });
  }
})();
