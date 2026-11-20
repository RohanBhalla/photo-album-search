// Photo Album frontend: search (GET /search) and upload (PUT /photos/{object})
// through the API Gateway generated SDK (SDK1).

(function () {
  "use strict";

  // --- SDK fixes -------------------------------------------------------------
  // The generated SDK was written for JSON bodies and breaks binary uploads twice:
  //  1. apiGatewayClient.makeRequest drops any body with no own enumerable keys
  //     (Object.keys(body).length === 0), and a File has none -> empty upload.
  //     Fix: tag the file with one enumerable property before sending (see binaryBody).
  //  2. utils.copy() rebuilds the body with obj.constructor(), which throws for
  //     File/Blob ("use the 'new' operator"). Fix: pass binary bodies through as-is.
  // Done here, not in front-end/sdk/, so regenerating the SDK doesn't undo it.
  function binaryBody(blob) {
    Object.defineProperty(blob, "isBinaryBody", { value: true, enumerable: true });
    return blob;
  }
  var originalCopy = apiGateway.core.utils.copy;
  apiGateway.core.utils.copy = function (obj) {
    if (obj instanceof Blob || obj instanceof ArrayBuffer || ArrayBuffer.isView(obj)) return obj;
    return originalCopy(obj);
  };

  var config = window.APP_CONFIG || {};
  if (!config.apiKey) {
    document.getElementById("search-status").textContent =
      "Missing API key: create front-end/config.js (see config.example.js).";
  }
  var client = apigClientFactory.newClient({ apiKey: config.apiKey });

  var MAX_BYTES = 10 * 1024 * 1024; // API Gateway payload limit
  var ALLOWED_TYPES = ["image/jpeg", "image/png"];

  var $ = function (id) { return document.getElementById(id); };

  // --- Search ----------------------------------------------------------------
  $("search-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var q = $("search-input").value.trim();
    if (!q) return;
    setStatus("search-status", "Searching…");
    $("results").innerHTML = "";

    client.searchGet({ q: q }, undefined, {})
      .then(function (response) {
        var results = (response.data && response.data.results) || [];
        renderResults(results);
        setStatus("search-status", results.length
          ? results.length + " photo" + (results.length === 1 ? "" : "s") + " found for “" + q + "”"
          : "No photos found for “" + q + "”.");
      })
      .catch(function (error) {
        setStatus("search-status", "Search failed: " + describeError(error), true);
      });
  });

  function renderResults(results) {
    var grid = $("results");
    results.forEach(function (photo) {
      var figure = document.createElement("figure");
      figure.className = "photo";

      var img = document.createElement("img");
      img.src = photo.url;
      img.alt = (photo.labels || []).join(", ");
      img.loading = "lazy";

      var caption = document.createElement("figcaption");
      (photo.labels || []).forEach(function (label) {
        var chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = label;
        caption.appendChild(chip);
      });

      figure.appendChild(img);
      figure.appendChild(caption);
      grid.appendChild(figure);
    });
  }

  // --- Custom label tags -----------------------------------------------------
  var tags = [];
  var tagInput = $("tag-input");

  function addTag(text) {
    text.split(",").forEach(function (part) {
      var label = part.trim();
      var exists = tags.some(function (t) { return t.toLowerCase() === label.toLowerCase(); });
      if (label && !exists) tags.push(label);
    });
    tagInput.value = "";
    renderTags();
  }

  function renderTags() {
    var box = $("tag-box");
    box.querySelectorAll(".chip").forEach(function (chip) { chip.remove(); });
    tags.forEach(function (label, i) {
      var chip = document.createElement("span");
      chip.className = "chip removable";
      chip.textContent = label;
      var remove = document.createElement("button");
      remove.type = "button";
      remove.setAttribute("aria-label", "Remove " + label);
      remove.textContent = "×";
      remove.addEventListener("click", function () { tags.splice(i, 1); renderTags(); });
      chip.appendChild(remove);
      box.insertBefore(chip, tagInput);
    });
  }

  tagInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addTag(tagInput.value);
    } else if (event.key === "Backspace" && !tagInput.value && tags.length) {
      tags.pop();
      renderTags();
    }
  });
  tagInput.addEventListener("blur", function () { if (tagInput.value.trim()) addTag(tagInput.value); });
  $("tag-box").addEventListener("click", function () { tagInput.focus(); });

  // --- Upload ----------------------------------------------------------------
  $("upload-form").addEventListener("submit", function (event) {
    event.preventDefault();
    if (tagInput.value.trim()) addTag(tagInput.value); // include a label typed but not yet "entered"

    var file = $("upload-file").files[0];
    if (!file) return;
    if (ALLOWED_TYPES.indexOf(file.type) === -1) {
      return setStatus("upload-status", "Please choose a JPEG or PNG image.", true);
    }
    if (file.size > MAX_BYTES) {
      return setStatus("upload-status", "That file is over 10 MB. Please choose a smaller one.", true);
    }

    var key = Date.now() + "-" + safeName(file.name); // timestamp stops same-name photos overwriting each other
    var params = {
      object: key,
      "Content-Type": file.type,
      // Custom labels as a comma-separated list, e.g. "Sam, Sally"
      "x-amz-meta-customLabels": tags.join(", ")
    };

    $("upload-button").disabled = true;
    setStatus("upload-status", "Uploading…");

    // Copy into a fresh Blob so the tag never touches the user's File object.
    var body = binaryBody(new Blob([file], { type: file.type }));

    client.photosObjectPut(params, body, {})
      .then(function () {
        setStatus("upload-status", "Uploaded “" + file.name + "”" +
          (tags.length ? " with labels: " + tags.join(", ") : "") +
          ". It will show up in search within a few seconds.");
        $("upload-form").reset();
        tags = [];
        renderTags();
      })
      .catch(function (error) {
        setStatus("upload-status", "Upload failed: " + describeError(error), true);
      })
      .then(function () { $("upload-button").disabled = false; });
  });

  // --- Helpers ---------------------------------------------------------------
  function safeName(name) {
    return name.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "photo";
  }

  function setStatus(id, text, isError) {
    var el = $(id);
    el.textContent = text;
    el.classList.toggle("error", !!isError);
  }

  function describeError(error) {
    var r = error && error.response;
    if (r) return r.status + " " + ((r.data && r.data.message) || r.statusText || "");
    return (error && error.message) || "network error";
  }
})();
