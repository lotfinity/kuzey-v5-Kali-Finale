(function () {
  function getCookie(name) {
    var value = "; " + document.cookie;
    var parts = value.split("; " + name + "=");
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  function formatTime(value) {
    if (!value) return "";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function formatDateTime(value) {
    if (!value) return "";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    var now = new Date();
    if (date.toDateString() === now.toDateString()) return formatTime(value);
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function setStatus(widget, text) {
    var status = widget.querySelector("[data-wa-status]");
    if (status) status.textContent = text;
  }

  function makeStatus(text) {
    var node = document.createElement("div");
    node.className = "WA_Chat_Status";
    node.textContent = text;
    return node;
  }

  function appendMessage(widget, message, seenIds) {
    var box = widget.querySelector("[data-wa-messages]");
    var empty = widget.querySelector("[data-wa-empty]");
    if (!box || !message) return;
    if (empty) empty.hidden = true;
    var key = String(message.id || message.wahaMessageId || "");
    if (key && seenIds.has(key)) return;
    if (key) seenIds.add(key);

    if (box.querySelector(".WA_Chat_Status, .WA_Chat_Empty")) {
      box.textContent = "";
    }

    var row = document.createElement("div");
    row.className = "WA_Message";

    var bubble = document.createElement("div");
    bubble.className = "WA_MessageBubble " + (message.direction === "out" ? "sent" : "received");
    bubble.appendChild(document.createTextNode(message.body || "[" + (message.type || "message") + "]"));

    var meta = document.createElement("span");
    meta.className = "WA_MessageMeta";
    var time = document.createElement("span");
    time.className = "time";
    time.textContent = formatTime(message.sentAt);
    meta.appendChild(time);
    if (message.direction === "out") {
      var tick = document.createElement("span");
      tick.className = "WA_Tick";
      tick.textContent = "✓✓";
      meta.appendChild(tick);
    }

    bubble.appendChild(meta);
    row.appendChild(bubble);
    box.appendChild(row);
    box.scrollTop = box.scrollHeight;
    if (box.parentElement) box.parentElement.scrollTop = box.parentElement.scrollHeight;
  }

  function renderMessages(widget, messages) {
    var box = widget.querySelector("[data-wa-messages]");
    var empty = widget.querySelector("[data-wa-empty]");
    if (!box) return;
    box.textContent = "";
    var seenIds = widget._waSeenIds || new Set();
    seenIds.clear();
    widget._waSeenIds = seenIds;
    if (!messages || !messages.length) {
      if (empty) {
        empty.hidden = false;
        empty.textContent = "Aucun message pour le moment.";
      } else {
        box.appendChild(makeStatus("Aucun message pour le moment."));
      }
      return;
    }
    if (empty) empty.hidden = true;
    messages.forEach(function (message) {
      appendMessage(widget, message, seenIds);
    });
    box.scrollTop = box.scrollHeight;
    if (box.parentElement) box.parentElement.scrollTop = box.parentElement.scrollHeight;
  }

  function nativeWaHref(phone, text) {
    var digits = String(phone || "").replace(/\D+/g, "");
    if (!digits) return "#";
    var href = "https://wa.me/" + digits;
    if (text) href += "?text=" + encodeURIComponent(text);
    return href;
  }

  function autoSize(input) {
    if (!input) return;
    input.style.height = "auto";
    input.style.height = Math.min(Math.max(input.scrollHeight, 50), 118) + "px";
  }

  function initWidget(widget) {
    var listingId = widget.getAttribute("data-listing-id");
    var standalone = widget.getAttribute("data-wa-standalone") === "1";
    var globalMode = standalone || !listingId;
    var apiRoot = widget.getAttribute("data-api-root") || "/api/whatsapp";
    var listingPhone = widget.getAttribute("data-listing-phone") || "";
    var toggle = widget.querySelector("[data-wa-toggle]");
    var close = widget.querySelector("[data-wa-close]");
    var titleEl = widget.querySelector("[data-wa-title]");
    var form = widget.querySelector("[data-wa-form]");
    var input = widget.querySelector("[data-wa-input]");
    var send = widget.querySelector("[data-wa-send]");
    var suggest = widget.querySelector("[data-wa-suggest]");
    var icebreaker = widget.querySelector("[data-wa-icebreaker]");
    var nativeLinks = widget.querySelectorAll("[data-wa-native]");
    var unreadBadge = widget.querySelector("[data-wa-unread]");
    var inboxPane = widget.querySelector("[data-wa-inbox]");
    var listEl = widget.querySelector("[data-wa-conversations]");
    var messagePane = widget.querySelector("[data-wa-message-pane]");
    var socket = null;
    var reconnectTimer = null;
    var sendRefreshTimer = null;
    var reconnectRecovery = false;
    var loadedOnce = false;
    var unreadCount = 0;
    var activeConversationId = "";
    var conversations = [];
    var deviceTime = widget.querySelector("[data-wa-device-time]");

    widget.classList.toggle("is-global", globalMode);

    function setNativeLinks(text) {
      nativeLinks.forEach(function (native) {
        native.href = nativeWaHref(listingPhone, text || "");
      });
    }
    setNativeLinks();
    function updateDeviceTime() {
      if (deviceTime) deviceTime.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }
    updateDeviceTime();
    window.setInterval(updateDeviceTime, 1000);

    function endpoint(suffix) {
      return apiRoot.replace(/\/+$/, "") + "/listing/" + encodeURIComponent(listingId) + suffix;
    }

    function conversationEndpoint(conversationId, suffix) {
      return apiRoot.replace(/\/+$/, "") + "/conversation/" + encodeURIComponent(conversationId) + suffix;
    }

    function indexEndpoint() {
      return apiRoot.replace(/\/+$/, "") + "/conversations";
    }

    function fetchJsonWithTimeout(url, options, timeoutMs) {
      var controller = window.AbortController ? new AbortController() : null;
      var timer = window.setTimeout(function () {
        if (controller) controller.abort();
      }, timeoutMs || 45000);
      var requestOptions = Object.assign({}, options || {});
      if (controller) requestOptions.signal = controller.signal;
      return fetch(url, requestOptions)
        .then(function (response) { return response.json(); })
        .finally(function () {
          window.clearTimeout(timer);
        });
    }

    function setUnreadCount(count) {
      unreadCount = Math.max(0, count || 0);
      if (!unreadBadge) return;
      unreadBadge.hidden = unreadCount < 1;
      unreadBadge.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
    }

    function setOpen(open) {
      widget.classList.toggle("is-open", open);
      var dialog = widget.querySelector(".WA_ChatBox");
      if (dialog) dialog.setAttribute("aria-hidden", open ? "false" : "true");
      if (open) setUnreadCount(0);
      if (open) {
        if (globalMode) {
          loadConversations();
          connectSocket();
        } else {
          loadMessages(!loadedOnce);
          connectSocket();
        }
        if (input && !input.disabled) window.setTimeout(function () { input.focus(); }, 80);
      }
    }

    function setComposerEnabled(enabled) {
      var canDraft = globalMode ? Boolean(activeConversationId) : Boolean(listingId);
      if (input) input.disabled = !canDraft;
      if (send) send.disabled = !enabled;
      if (suggest) suggest.disabled = globalMode || !enabled;
      if (icebreaker) icebreaker.disabled = !canDraft;
    }

    function setHeader(conversation) {
      if (!titleEl) return;
      if (!conversation) {
        titleEl.textContent = globalMode ? "Conversations" : (widget.getAttribute("data-contact-name") || "WhatsApp");
        return;
      }
      listingPhone = conversation.phoneNumber || listingPhone || "";
      setNativeLinks(input ? input.value : "");
      titleEl.textContent = conversation.displayName || conversation.phoneNumber || conversation.listingTitle || "Conversation";
    }

    function icebreakerMessage() {
      var pageUrl = window.location.href;
      return "Merhaba, bu kişiye sahibinin ilanı üzerinden ulaşıyorum. İlan hâlâ satışta mı, durumu nedir? Referans olması için ilan linkini bırakıyorum: " + pageUrl;
    }

    function fillIcebreakerDraft() {
      if (!input) return;
      input.value = icebreakerMessage();
      autoSize(input);
      setNativeLinks(input.value);
      input.focus();
    }

    function loadMessages(sync) {
      if (globalMode) return loadActiveConversation(sync);
      if (!listingId) return Promise.resolve();
      if (!loadedOnce) {
        setStatus(widget, "Loading messages...");
      }
      return fetch(endpoint("/conversation?limit=60&sync=" + (sync ? "1" : "0")), {
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          loadedOnce = true;
          if (!data.ok) throw new Error(data.error || "Could not load messages.");
          renderMessages(widget, data.messages || []);
          setComposerEnabled(Boolean(data.wahaConfigured));
          if (data.syncError) {
            setStatus(widget, "Showing saved messages");
          } else if (data.wahaConfigured) {
            setStatus(widget, "Connected to " + (data.displayName || data.phoneNumber || "WhatsApp"));
          } else {
            setStatus(widget, "WAHA not configured");
          }
        })
        .catch(function (error) {
          setComposerEnabled(false);
          setStatus(widget, error.message || "Could not load messages.");
        });
    }

    function conversationTitle(conversation) {
      return conversation.displayName || conversation.phoneNumber || "Contact WhatsApp";
    }

    function conversationSubline(conversation) {
      var bits = [];
      if (conversation.listingTitle) bits.push(conversation.listingTitle);
      if (conversation.latestMessage && conversation.latestMessage.body) bits.push(conversation.latestMessage.body);
      return bits.join(" · ") || conversation.chatId || "";
    }

    function formatConversationPrice(conversation) {
      if (!conversation || !conversation.listingPrice) return "";
      if (window.KuzeyCurrency) return window.KuzeyCurrency.format(conversation.listingPrice);
      return conversation.listingPrice;
    }

    function totalUnread(items) {
      return (items || []).reduce(function (sum, item) {
        return sum + Math.max(0, item.unreadCount || 0);
      }, 0);
    }

    function renderConversations(items) {
      if (!listEl) return;
      listEl.textContent = "";
      if (!items || !items.length) {
        listEl.appendChild(makeStatus("Aucune conversation WhatsApp enregistrée."));
        return;
      }
      items.forEach(function (conversation) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "WA_ConversationItem" + (String(conversation.id) === String(activeConversationId) ? " is-active" : "");
        button.dataset.conversationId = conversation.id;
        var unread = Math.max(0, conversation.unreadCount || 0);
        var image = conversation.listingImage || "";
        var latest = conversation.latestMessage || {};
        button.innerHTML =
          '<span class="WA_ConversationAvatar">' +
            (image ? '<img src="' + escapeHtml(image) + '" alt="">' : '<i class="fab fa-whatsapp"></i>') +
          '</span>' +
          '<span class="WA_ConversationMain">' +
            '<span class="WA_ConversationTop"><strong>' + escapeHtml(conversationTitle(conversation)) + '</strong><time>' + escapeHtml(formatDateTime(latest.sentAt || conversation.updatedAt)) + '</time></span>' +
            '<span class="WA_ConversationSub">' + escapeHtml(conversationSubline(conversation)) + '</span>' +
            (conversation.listingPrice ? '<span class="WA_ConversationPrice">' + escapeHtml(formatConversationPrice(conversation)) + '</span>' : '') +
          '</span>' +
          (unread ? '<span class="WA_ConversationUnread">' + (unread > 99 ? '99+' : unread) + '</span>' : '');
        button.addEventListener("click", function () {
          activeConversationId = String(conversation.id);
          renderConversations(conversations);
          loadActiveConversation(false);
        });
        listEl.appendChild(button);
      });
    }

    function loadConversations() {
      if (!globalMode) return Promise.resolve();
      if (inboxPane) inboxPane.hidden = false;
      if (messagePane) messagePane.classList.toggle("has-inbox", true);
      setStatus(widget, "Chargement des conversations...");
      return fetch(indexEndpoint() + "?limit=80", {
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || "Impossible de charger les conversations.");
          loadedOnce = true;
          conversations = data.conversations || [];
          setUnreadCount(data.totalUnread || totalUnread(conversations));
          renderConversations(conversations);
          if (!activeConversationId && conversations.length) {
            activeConversationId = String(conversations[0].id);
            renderConversations(conversations);
            return loadActiveConversation(false);
          }
          if (!conversations.length) {
            setHeader(null);
            setComposerEnabled(false);
            renderMessages(widget, []);
            setStatus(widget, "Aucune conversation enregistrée");
          }
        })
        .catch(function (error) {
          setComposerEnabled(false);
          if (listEl) {
            listEl.textContent = "";
            listEl.appendChild(makeStatus(error.message || "Impossible de charger les conversations."));
          }
          setStatus(widget, error.message || "Impossible de charger les conversations.");
        });
    }

    function loadActiveConversation(sync) {
      if (!activeConversationId) {
        setComposerEnabled(false);
        renderMessages(widget, []);
        return Promise.resolve();
      }
      setStatus(widget, "Chargement des messages...");
      return fetch(conversationEndpoint(activeConversationId, "/messages?limit=90&sync=" + (sync ? "1" : "0")), {
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || "Impossible de charger les messages.");
          setHeader(data.conversation);
          renderMessages(widget, data.messages || []);
          setComposerEnabled(Boolean(data.wahaConfigured));
          setStatus(widget, data.wahaConfigured ? "Conversation prête" : "WAHA non configuré");
        })
        .catch(function (error) {
          setComposerEnabled(false);
          setStatus(widget, error.message || "Impossible de charger les messages.");
        });
    }

    function socketUrl() {
      var scheme = window.location.protocol === "https:" ? "wss" : "ws";
      if (globalMode) return scheme + "://" + window.location.host + "/ws/whatsapp/index/";
      return scheme + "://" + window.location.host + "/ws/whatsapp/listing/" + encodeURIComponent(listingId) + "/";
    }

    function connectSocket() {
      if ((!listingId && !globalMode) || socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      try {
        socket = new WebSocket(socketUrl());
      } catch (error) {
        setStatus(widget, "Realtime unavailable");
        return;
      }
      socket.onopen = function () {
        if (loadedOnce) setStatus(widget, "Realtime connected");
        if (reconnectRecovery && loadedOnce) loadMessages(false);
        reconnectRecovery = false;
      };
      socket.onmessage = function (event) {
        var data = {};
        try { data = JSON.parse(event.data || "{}"); } catch (error) { return; }
        if (data.type === "whatsapp.message" && data.message) {
          if (!globalMode || data.conversation && String(data.conversation.id) === String(activeConversationId)) {
            appendMessage(widget, data.message, widget._waSeenIds || (widget._waSeenIds = new Set()));
          }
          if (sendRefreshTimer) {
            window.clearTimeout(sendRefreshTimer);
            sendRefreshTimer = null;
          }
          if (globalMode) {
            loadConversations();
          } else if (widget.classList.contains("is-open")) {
            setStatus(widget, "Realtime connected");
          } else {
            setUnreadCount(unreadCount + 1);
          }
        } else if (globalMode && data.type === "whatsapp.conversation_updated") {
          loadConversations();
        }
      };
      socket.onclose = function () {
        socket = null;
        reconnectRecovery = true;
        reconnectTimer = window.setTimeout(connectSocket, 2500);
      };
      socket.onerror = function () {
        setStatus(widget, "Realtime reconnecting");
      };
    }

    function disconnectSocket() {
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (socket) {
        socket.onclose = null;
        socket.close();
        socket = null;
      }
    }

    if (toggle) {
      toggle.addEventListener("click", function () {
        setOpen(!widget.classList.contains("is-open"));
      });
    }
    if (close) {
      close.addEventListener("click", function () { setOpen(false); });
    }
    if (input) {
      input.addEventListener("input", function () {
        autoSize(input);
        setNativeLinks(input.value || "");
      });
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          if (form) form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit"));
        }
      });
    }
    if (suggest) {
      suggest.addEventListener("click", function () {
        if (globalMode || !listingId || !input || suggest.disabled) return;
        suggest.disabled = true;
        setStatus(widget, "Drafting reply...");
        var slowTimer = window.setTimeout(function () {
          setStatus(widget, "AI is still drafting...");
        }, 7000);
        fetchJsonWithTimeout(endpoint("/suggest"), {
          method: "POST",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken")
          },
          credentials: "same-origin",
          body: JSON.stringify({ draft: input.value || "" })
        }, 45000)
          .then(function (data) {
            if (!data.ok) throw new Error(data.error || "Suggestion failed.");
            input.value = data.suggestion || "";
            autoSize(input);
            setStatus(widget, "Suggested reply ready");
            input.focus();
          })
          .catch(function (error) {
            var message = error && error.message ? error.message : "";
            if (error && error.name === "AbortError" || /timed out|timeout/i.test(message)) {
              setStatus(widget, "AI suggestion timed out. Try again.");
            } else {
              setStatus(widget, message || "Suggestion failed.");
            }
          })
          .finally(function () {
            window.clearTimeout(slowTimer);
            suggest.disabled = false;
          });
      });
    }
    if (icebreaker) {
      icebreaker.addEventListener("click", function () {
        if (!input) return;
        fillIcebreakerDraft();
        setStatus(widget, "Icebreaker loaded");
      });
    }
    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if ((!listingId && !activeConversationId) || !input || (send && send.disabled)) return;
        var text = input.value.trim();
        if (!text) return;
        setComposerEnabled(false);
        setStatus(widget, "Sending...");
        fetch(globalMode ? conversationEndpoint(activeConversationId, "/send") : endpoint("/send"), {
          method: "POST",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken")
          },
          credentials: "same-origin",
          body: JSON.stringify({ message: text })
        })
          .then(function (response) { return response.json(); })
          .then(function (data) {
            if (!data.ok) throw new Error(data.error || "Message failed.");
            input.value = "";
            autoSize(input);
            if (sendRefreshTimer) window.clearTimeout(sendRefreshTimer);
            sendRefreshTimer = window.setTimeout(function () {
              sendRefreshTimer = null;
              loadMessages(false);
              if (globalMode) loadConversations();
            }, 1200);
          })
          .catch(function (error) {
            setStatus(widget, error.message || "Message failed.");
          })
          .finally(function () {
            setComposerEnabled(true);
            if (input) input.focus();
          });
      });
    }

    if (globalMode) {
      if (inboxPane) inboxPane.hidden = false;
      setHeader(null);
      setComposerEnabled(false);
      setStatus(widget, "Boîte de réception WhatsApp");
      connectSocket();
      if (standalone) setOpen(true);
      else loadConversations();
    } else if (!listingId) {
      setComposerEnabled(false);
      setStatus(widget, "Open a listing to chat");
    } else {
      connectSocket();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".WA_Chat_Widget").forEach(initWidget);
  });
})();
