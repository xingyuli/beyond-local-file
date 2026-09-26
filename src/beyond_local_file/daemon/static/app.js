// Resolve UI client: sequential, two-way merge (ADR 0025).
//
// The daemon serves hub-now and every replica's live content once, per GET. This script owns
// the whole interactive flow from there: diffing, chunk-accept (via CodeMirror's own arrows),
// round-to-round accumulation, and the final submit. Same-as-hub replicas are listed but not
// opened; the rest are merged one at a time, in order, until submit is enabled.
(function () {
  "use strict";

  var NAV_COLLAPSE_KEY = "blf-resolve-nav-collapsed";

  function navShortcutLabel() {
    return /Mac|iPhone|iPad/.test(navigator.platform) ? "Cmd+B" : "Ctrl+B";
  }

  function refreshEditors() {
    var nodes = document.querySelectorAll(".CodeMirror");
    for (var i = 0; i < nodes.length; i += 1) {
      if (nodes[i].CodeMirror) {
        nodes[i].CodeMirror.refresh();
      }
    }
    window.dispatchEvent(new Event("resize"));
  }

  function setNavCollapsed(collapsed) {
    document.body.classList.toggle("nav-collapsed", collapsed);
    var toggle = document.getElementById("nav-toggle");
    if (toggle) {
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      toggle.setAttribute("aria-label", collapsed ? "Show files" : "Hide files");
    }
    try {
      sessionStorage.setItem(NAV_COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch (err) {
      // sessionStorage can throw in a blocked iframe; collapse still applies for this page.
    }
    refreshEditors();
  }

  function navIsCollapsed() {
    return document.body.classList.contains("nav-collapsed");
  }

  function wireNavToggle() {
    var toggle = document.getElementById("nav-toggle");
    var keys = document.getElementById("nav-toggle-keys");
    if (keys) {
      keys.textContent = navShortcutLabel();
    }
    if (!toggle) {
      return;
    }
    var stored = false;
    try {
      stored = sessionStorage.getItem(NAV_COLLAPSE_KEY) === "1";
    } catch (err) {
      stored = false;
    }
    if (stored) {
      setNavCollapsed(true);
    }
    toggle.addEventListener("click", function () {
      setNavCollapsed(!navIsCollapsed());
    });
    document.addEventListener("keydown", function (event) {
      if (event.altKey || event.shiftKey) {
        return;
      }
      if (event.key !== "b" && event.key !== "B") {
        return;
      }
      var mac = /Mac|iPhone|iPad/.test(navigator.platform);
      var chord = mac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
      if (!chord) {
        return;
      }
      event.preventDefault();
      setNavCollapsed(!navIsCollapsed());
    });
  }

  wireNavToggle();

  var stateEl = document.getElementById("resolve-state");
  var mount = document.getElementById("resolve-app");
  if (!stateEl || !mount) {
    return;
  }
  var state = JSON.parse(stateEl.textContent || "{}");
  var params = new URLSearchParams(window.location.search);

  var pending = state.replicas.filter(function (replica) {
    return !replica.same_as_hub;
  });
  var mergedPaths = Object.create(null);
  var roundIndex = 0;
  var leftText = state.binary ? null : state.hub_now;
  var winnerSource = "hub";
  var mv = null;
  var submitted = false;

  function currentReplica() {
    return pending[roundIndex];
  }

  function allDone() {
    return roundIndex >= pending.length;
  }

  function replicaByPath(path) {
    for (var i = 0; i < state.replicas.length; i += 1) {
      if (state.replicas[i].path === path) {
        return state.replicas[i];
      }
    }
    return null;
  }

  function statusOf(replica) {
    if (replica.same_as_hub) {
      return "same as hub";
    }
    if (mergedPaths[replica.path]) {
      return "merged";
    }
    var current = currentReplica();
    if (current && current.path === replica.path) {
      return "current";
    }
    return "pending";
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text != null) {
      node.textContent = text;
    }
    return node;
  }

  function render() {
    mv = null;
    mount.innerHTML = "";
    mount.appendChild(buildHeader());
    mount.appendChild(buildStage());
    // Mount CodeMirror only after the whole tree is attached, so it measures real dimensions.
    if (state.binary) {
      return;
    }
    if (allDone()) {
      mountReview();
    } else {
      mountEditor();
    }
  }

  function buildHeader() {
    // One toolbar row, not two: the common path prefix, every replica as a small two-line chip
    // (label on top, status below — a status word next to the label made every chip too wide to
    // fit more than one or two per row), and submit, all sharing the row a lone button used to
    // waste by itself. No project/path title either — the left nav already highlights the open
    // item (data-current), so repeating it in text would be the same information twice.
    var header = el("div", "resolve-header");
    if (state.common_prefix) {
      header.appendChild(el("div", "common-prefix", state.common_prefix));
    }
    var ul = el("ul", "replica-chip-list");
    state.replicas.forEach(function (replica) {
      var status = statusOf(replica);
      var li = el("li", "replica-row replica-" + status.replace(/ /g, "-"));
      li.title = replica.clause ? replica.label + " — " + replica.clause : replica.label;
      li.appendChild(el("div", "replica-label", replica.label));
      li.appendChild(el("div", "replica-status", status));
      ul.appendChild(li);
    });
    header.appendChild(ul);
    var remaining = pending.length - roundIndex;
    var submit = el("button", "btn btn-primary", allDone() ? "Submit" : "Submit (" + remaining + " left)");
    submit.type = "button";
    submit.id = "submit-resolve";
    submit.disabled = !allDone() || submitted;
    submit.addEventListener("click", onSubmit);
    header.appendChild(submit);
    return header;
  }

  function buildStage() {
    var stage = el("section", "resolve-stage");
    if (allDone()) {
      stage.appendChild(buildReviewStage());
      return stage;
    }
    stage.appendChild(state.binary ? buildBinaryStage() : buildTextStage());
    return stage;
  }

  function buildReviewStage() {
    var wrap = el("div", "review-stage");
    wrap.appendChild(el("p", "all-done", "All replicas merged. Review the result below, then submit."));
    if (state.binary) {
      var winner = replicaByPath(winnerSource);
      var title = winner ? winner.label : "hub-now";
      var hash = winner ? winner.hash : state.hub_hash;
      var size = winner ? winner.size : state.hub_size;
      wrap.appendChild(buildBinaryCard(title, hash, size, null, null));
    } else {
      var reviewMount = document.createElement("div");
      reviewMount.id = "review-mount";
      wrap.appendChild(reviewMount);
    }
    return wrap;
  }

  function buildBinaryStage() {
    var replica = currentReplica();
    var wrap = el("div", "binary-stage");
    var winner = replicaByPath(winnerSource);
    var currentTitle = winner ? "current: " + winner.label : "current: hub-now";
    var currentHash = winner ? winner.hash : state.hub_hash;
    var currentSize = winner ? winner.size : state.hub_size;
    wrap.appendChild(
      buildBinaryCard(currentTitle, currentHash, currentSize, "keep current", function () {
        advanceRound();
      })
    );
    wrap.appendChild(
      buildBinaryCard(replica.label, replica.hash, replica.size, "take this replica", function () {
        winnerSource = replica.path;
        advanceRound();
      })
    );
    return wrap;
  }

  function buildBinaryCard(title, hash, size, actionLabel, onClick) {
    var card = el("div", "binary-card");
    card.appendChild(el("h3", null, title));
    card.appendChild(el("p", "binary-meta", "hash " + hash + " size " + size));
    if (actionLabel) {
      var button = el("button", "btn", actionLabel);
      button.type = "button";
      button.addEventListener("click", onClick);
      card.appendChild(button);
    }
    return card;
  }

  function buildTextStage() {
    var wrap = el("div", "text-stage");
    var labels = el("div", "merge-labels");
    var names = roundIndex === 0 ? ["hub-now", "result", "replica-now"] : ["current", "result", "replica-now"];
    names.forEach(function (name) {
      labels.appendChild(el("span", null, name));
    });
    wrap.appendChild(labels);
    var editorMount = document.createElement("div");
    editorMount.id = "merge-mount";
    wrap.appendChild(editorMount);
    var controls = el("div", "hunk-controls");
    var markButton = el("button", "btn btn-primary", "mark as merged");
    markButton.type = "button";
    markButton.id = "mark-merged";
    markButton.addEventListener("click", function () {
      leftText = mv ? mv.editor().getValue() : leftText;
      advanceRound();
    });
    controls.appendChild(markButton);
    wrap.appendChild(controls);
    return wrap;
  }

  function mountEditor() {
    var editorMount = document.getElementById("merge-mount");
    var replica = currentReplica();
    if (!editorMount || !replica || !window.CodeMirror) {
      return;
    }
    mv = window.CodeMirror.MergeView(editorMount, {
      value: leftText,
      origLeft: leftText,
      orig: replica.text,
      lineNumbers: true,
      lineWrapping: true,
      mode: "text/plain",
      spellcheck: false,
      highlightDifferences: true,
      connect: "align",
      collapseIdentical: true,
      revertButtons: true,
      // CodeMirror's default wording ("Revert chunk") reads backwards in a merge: clicking the
      // arrow pulls a side's chunk into the result, it does not undo anything.
      phrases: { "Revert chunk": "Accept this chunk" },
    });
    disableSpellcheck(editorMount);
    refreshMerge();
    window.requestAnimationFrame(refreshMerge);
    wireAcceptHover(editorMount);
  }

  function refreshMerge() {
    if (!mv) {
      return;
    }
    if (mv.editor()) {
      mv.editor().refresh();
    }
    if (mv.left && mv.left.orig) {
      mv.left.orig.refresh();
    }
    if (mv.right && mv.right.orig) {
      mv.right.orig.refresh();
    }
  }

  // Sequential merge only pulls from the replica on the right. After that, CodeMirror treats
  // hub-now vs result as a second donor and paints "Accept →" on the left — that would copy
  // hub back over the merge, i.e. undo, not accept. Hide those. Hovering a real (right)
  // Accept paints both sides of that hunk so it is obvious which RESULT lines will be replaced.
  var pairMarks = [];

  function clearPairHover() {
    for (var i = 0; i < pairMarks.length; i += 1) {
      var mark = pairMarks[i];
      mark.cm.removeLineClass(mark.line, "background", "merge-pair-hover");
    }
    pairMarks = [];
  }

  function markPairRange(cm, from, to) {
    if (!cm) {
      return;
    }
    if (from === to) {
      var line = from > 0 ? from - 1 : 0;
      cm.addLineClass(line, "background", "merge-pair-hover");
      pairMarks.push({ cm: cm, line: line });
      return;
    }
    for (var i = from; i < to; i += 1) {
      cm.addLineClass(i, "background", "merge-pair-hover");
      pairMarks.push({ cm: cm, line: i });
    }
  }

  function wireAcceptHover(root) {
    root.addEventListener("mouseover", function (event) {
      var btn = event.target.closest(".CodeMirror-merge-copybuttons-right .CodeMirror-merge-copy");
      if (!btn || !btn.chunk || !mv) {
        return;
      }
      clearPairHover();
      markPairRange(mv.editor(), btn.chunk.editFrom, btn.chunk.editTo);
      markPairRange(mv.right && mv.right.orig, btn.chunk.origFrom, btn.chunk.origTo);
    });
    root.addEventListener("mouseout", function (event) {
      var fromBtn = event.target.closest(".CodeMirror-merge-copybuttons-right .CodeMirror-merge-copy");
      if (!fromBtn) {
        return;
      }
      var into = event.relatedTarget && event.relatedTarget.closest
        ? event.relatedTarget.closest(".CodeMirror-merge-copybuttons-right .CodeMirror-merge-copy")
        : null;
      if (into !== fromBtn) {
        clearPairHover();
      }
    });
  }

  function mountReview() {
    var reviewMount = document.getElementById("review-mount");
    if (!reviewMount || !window.CodeMirror) {
      return;
    }
    var review = window.CodeMirror(reviewMount, {
      value: leftText,
      lineNumbers: true,
      lineWrapping: true,
      mode: "text/plain",
      readOnly: true,
      spellcheck: false,
    });
    disableSpellcheck(reviewMount);
    review.refresh();
  }

  // Some browsers still draw red underlines on CodeMirror's textarea / contenteditable even when
  // the option defaults to false; force the attribute off on every input the mount created.
  function disableSpellcheck(root) {
    if (!root) {
      return;
    }
    var nodes = root.querySelectorAll("textarea, [contenteditable]");
    for (var i = 0; i < nodes.length; i += 1) {
      nodes[i].setAttribute("spellcheck", "false");
      nodes[i].spellcheck = false;
    }
  }

  function advanceRound() {
    var replica = currentReplica();
    if (replica) {
      mergedPaths[replica.path] = true;
    }
    roundIndex += 1;
    render();
  }

  // At least one round has been merged (or the whole thing is done) and it has not been
  // submitted yet: leaving now — including re-clicking the very same nav item, which reloads the
  // page just the same — silently discards that progress. Warn once before either happens.
  // After the in-page confirm succeeds, navigation itself fires beforeunload; without this flag
  // the browser would ask a second time ("Leave site?") for the same discard the user just OK'd.
  var leaveConfirmed = false;

  function hasUnsavedProgress() {
    return !submitted && !leaveConfirmed && roundIndex > 0;
  }

  function askLeave() {
    return new Promise(function (resolve) {
      var existing = document.getElementById("leave-dialog");
      if (existing) {
        existing.remove();
      }
      var backdrop = el("div", "dialog-backdrop");
      backdrop.id = "leave-dialog";
      backdrop.setAttribute("role", "presentation");
      var dialog = el("div", "dialog");
      dialog.setAttribute("role", "alertdialog");
      dialog.setAttribute("aria-modal", "true");
      dialog.setAttribute("aria-labelledby", "leave-dialog-title");
      dialog.appendChild(el("h3", null, "Leave this merge?"));
      dialog.appendChild(
        el("p", null, "Unsubmitted merge progress for this path will be discarded.")
      );
      var actions = el("div", "dialog-actions");
      var stay = el("button", "btn", "Stay");
      stay.type = "button";
      var leave = el("button", "btn btn-primary", "Leave");
      leave.type = "button";
      actions.appendChild(stay);
      actions.appendChild(leave);
      dialog.appendChild(actions);
      backdrop.appendChild(dialog);
      document.body.appendChild(backdrop);
      leave.focus();

      function finish(ok) {
        document.removeEventListener("keydown", onKey);
        backdrop.remove();
        resolve(ok);
      }
      function onKey(event) {
        if (event.key === "Escape") {
          event.preventDefault();
          finish(false);
        }
      }
      stay.addEventListener("click", function () {
        finish(false);
      });
      leave.addEventListener("click", function () {
        finish(true);
      });
      backdrop.addEventListener("click", function (event) {
        if (event.target === backdrop) {
          finish(false);
        }
      });
      document.addEventListener("keydown", onKey);
    });
  }

  function guardNavAway(event) {
    var link = event.target.closest ? event.target.closest("a") : null;
    if (!link || !hasUnsavedProgress()) {
      return;
    }
    event.preventDefault();
    var href = link.href;
    askLeave().then(function (ok) {
      if (!ok) {
        return;
      }
      leaveConfirmed = true;
      window.location.href = href;
    });
  }

  var navEl = document.querySelector("nav.index");
  if (navEl) {
    navEl.addEventListener("click", guardNavAway);
  }
  window.addEventListener("beforeunload", function (event) {
    if (hasUnsavedProgress()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  function post(payload) {
    return fetch(window.location.pathname + "?" + params.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (response) {
      return response.json();
    });
  }

  function onSubmit() {
    var submitButton = document.getElementById("submit-resolve");
    if (submitButton) {
      submitButton.disabled = true;
    }
    var payload = {
      action: "submit",
      project: params.get("project"),
      path: params.get("path"),
      binary: !!state.binary,
    };
    if (state.binary) {
      payload.winner_source = winnerSource;
    } else {
      payload.middle = leftText;
    }
    post(payload)
      .then(function (data) {
        submitted = true;
        var stage = document.querySelector(".resolve-stage");
        if (stage) {
          stage.appendChild(el("p", "submit-result", (data && data.note) || "Submitted."));
        }
      })
      .catch(function () {
        if (submitButton) {
          submitButton.disabled = false;
        }
      });
  }

  render();
})();
