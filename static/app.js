document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chatMessages');
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chatInput');
    const typingIndicator = document.getElementById('typingIndicator');
    const clearChatBtn = document.getElementById('clearChatBtn');
    const askAboutOrderBtn = document.getElementById('askAboutOrderBtn');
    const helpSearchInput = document.getElementById('helpSearchInput');
    const helpSearchBtn = document.getElementById('helpSearchBtn');

    // Simple Markdown to HTML formatter
    function formatMarkdown(text) {
        if (!text) return '';
        let formatted = text
            // Bold
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Inline code
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // Line breaks
            .replace(/\n/g, '<br>');

        return formatted;
    }

    // Append a message to chat
    function appendMessage(sender, text, meta = null) {
        const wrapper = document.createElement('div');
        wrapper.className = `message-wrapper ${sender}`;

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.textContent = sender === 'user' ? '👤' : '📦';

        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble';

        const content = document.createElement('div');
        content.className = 'msg-content';
        content.innerHTML = formatMarkdown(text);
        bubble.appendChild(content);

        // If assistant has LangGraph execution metadata, add reasoning accordion
        if (sender === 'assistant' && meta && meta.steps && meta.steps.length > 0) {
            const accordion = document.createElement('div');
            accordion.className = 'trace-accordion';
            
            const intentLabel = meta.intent ? `Intent: ${meta.intent.toUpperCase()}` : 'LangGraph Execution';
            const distLabel = meta.doc_distances && meta.doc_distances.length > 0 ? ` • Dist: ${meta.doc_distances[0].toFixed(4)}` : '';

            accordion.innerHTML = `
                <div class="trace-summary">
                    <span>⚡ <strong>${intentLabel}</strong>${distLabel}</span>
                    <span class="trace-toggle">▼ Details</span>
                </div>
                <div class="trace-details">
                    ${meta.steps.map(s => `<div>• ${escapeHtml(s)}</div>`).join('')}
                </div>
            `;

            accordion.addEventListener('click', () => {
                accordion.classList.toggle('expanded');
                const toggle = accordion.querySelector('.trace-toggle');
                toggle.textContent = accordion.classList.contains('expanded') ? '▲ Hide' : '▼ Details';
            });

            bubble.appendChild(accordion);
        }

        // If assistant has clickable orders list from ask_order_id_node
        if (sender === 'assistant' && meta && meta.orders_list && meta.orders_list.length > 0) {
            const container = document.createElement('div');
            container.className = 'interactive-orders-container';
            
            meta.orders_list.forEach(ord => {
                const card = document.createElement('button');
                card.type = 'button';
                card.className = 'interactive-order-card';
                card.setAttribute('data-query', `Where is my order ${ord.order_id}?`);
                
                let badgeClass = 'badge-transit';
                const st = (ord.status || '').toLowerCase();
                if (st.includes('delivered') || st.includes('pickup')) {
                    badgeClass = 'badge-success';
                } else if (st.includes('delayed') || st.includes('hold')) {
                    badgeClass = 'badge-warning';
                } else if (st.includes('returned')) {
                    badgeClass = 'badge-returned';
                }

                card.innerHTML = `
                    <div class="ioc-header">
                        <span class="ioc-icon">${ord.icon || '📦'}</span>
                        <div class="ioc-main">
                            <div class="ioc-title">${escapeHtml(ord.item)}</div>
                            <div class="ioc-sub">Order #${ord.order_id} • ${ord.price}</div>
                        </div>
                        <span class="ioc-badge ${badgeClass}">${escapeHtml(ord.status)}</span>
                    </div>
                    <div class="ioc-footer">
                        <span class="ioc-delivery">🚚 ${escapeHtml(ord.revised_delivery || 'In progress')}</span>
                        <span class="ioc-action">Track Details →</span>
                    </div>
                `;
                container.appendChild(card);
            });
            bubble.appendChild(container);
        }

        // Detect if the message contains Option 1, 2, 3 action choices
        if (sender === 'assistant' && text.includes('Option 1') && text.includes('Option 2')) {
            const actionChips = document.createElement('div');
            actionChips.className = 'quick-chips';
            actionChips.innerHTML = `
                <button class="chip" data-query="Option 1">1️⃣ Option 1: Free Replacement</button>
                <button class="chip" data-query="Option 2">2️⃣ Option 2: Instant Refund</button>
                <button class="chip" data-query="Option 3">3️⃣ Option 3: Phone Callback</button>
            `;
            bubble.appendChild(actionChips);
        }

        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);
        chatMessages.appendChild(wrapper);

        // Scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Send query to API
    async function handleSendQuery(queryText) {
        const query = queryText.trim();
        if (!query) return;

        // Display user message
        appendMessage('user', query);
        chatInput.value = '';
        chatInput.disabled = true;

        // Show typing indicator
        typingIndicator.classList.add('active');
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: query })
            });

            if (!response.ok) {
                throw new Error(`Server returned status: ${response.status}`);
            }

            const data = await response.json();
            
            // Display assistant message with LangGraph reasoning trace
            appendMessage('assistant', data.response, {
                intent: data.intent,
                steps: data.steps,
                doc_distances: data.doc_distances,
                order_id: data.order_id,
                orders_list: data.orders_list
            });

        } catch (error) {
            console.error('Chat error:', error);
            appendMessage('assistant', 'Sorry, I encountered an error communicating with the support agent. Please verify the server is running and try again.');
        } finally {
            typingIndicator.classList.remove('active');
            chatInput.disabled = false;
            chatInput.focus();
        }
    }

    // Form submit listener
    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        handleSendQuery(chatInput.value);
    });

    // Delegate click for suggestion chips anywhere in the chat
    document.addEventListener('click', (e) => {
        const chip = e.target.closest('[data-query]');
        if (chip) {
            const query = chip.getAttribute('data-query');
            if (query) {
                handleSendQuery(query);
            }
        }
    });

    // "Ask About This Order" button
    if (askAboutOrderBtn) {
        askAboutOrderBtn.addEventListener('click', () => {
            handleSendQuery("Order 112-9874561-3456789 why is it delayed and when will it arrive?");
        });
    }

    // Search bar listener
    if (helpSearchBtn && helpSearchInput) {
        helpSearchBtn.addEventListener('click', () => {
            if (helpSearchInput.value.trim()) {
                handleSendQuery(helpSearchInput.value.trim());
                helpSearchInput.value = '';
            }
        });
        helpSearchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && helpSearchInput.value.trim()) {
                e.preventDefault();
                handleSendQuery(helpSearchInput.value.trim());
                helpSearchInput.value = '';
            }
        });
    }

    // Clear Chat Button
    if (clearChatBtn) {
        clearChatBtn.addEventListener('click', () => {
            chatMessages.innerHTML = `
                <div class="message-wrapper assistant">
                    <div class="msg-avatar">📦</div>
                    <div class="msg-bubble">
                        <div class="msg-content">
                            Chat session refreshed! How can our <strong>Amazon Customer Support Assistant</strong> assist you?
                        </div>
                        <div class="quick-chips">
                            <button class="chip" data-query="why is my delivery delayed?">Why is my delivery delayed?</button>
                            <button class="chip" data-query="What is Amazon's Guaranteed Delivery policy?">Delivery Guarantees</button>
                            <button class="chip" data-query="How long do I have to pick up from an Amazon Locker?">Locker pickup window</button>
                        </div>
                    </div>
                </div>
            `;
        });
    }
});
