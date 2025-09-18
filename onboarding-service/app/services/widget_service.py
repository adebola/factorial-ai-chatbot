import os
import base64
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from jinja2 import Template
from ..services.dependencies import get_full_tenant_details, get_tenant_settings

# Note: Tenant model removed - tenant management now in OAuth2 server


class WidgetService:
    """Service for generating chat widget files for tenants"""
    
    def __init__(self, db: Session):
        self.db = db
        self.colors = {
            "primary": "#5D3EC1",  # Purple
            "secondary": "#C15D3E",  # Orange
            "accent": "#3EC15D",    # Green
            "white": "#FFFFFF",
            "gray": "#F5F5F5",
            "dark_gray": "#333333",
            "light_gray": "#E0E0E0"
        }
    
    async def generate_widget_files(self, tenant_id: str, access_token: Optional[str] = None) -> Dict[str, str]:
        """
        Generate all widget files for a tenant
        
        Args:
            tenant_id: tenant id information from OAuth2 server
        """
        
        # Store tenant_id for use in logo lookup
        self._tenant_id = tenant_id

        # Get tenant details if needed
        tenant_details = await get_full_tenant_details(tenant_id, access_token)
        tenant_name = tenant_details.get("name", "Unknown")
        
        # Get tenant settings for customization
        tenant_settings = get_tenant_settings(tenant_id, access_token)
        
        # Get logo information with chat logo data (URL or initials)
        logo_info = self._get_logo_info(tenant_settings, tenant_name)
        
        # Use settings values or defaults
        colors = self._get_colors(tenant_settings)
        
        from datetime import datetime

        # Determine environment and set appropriate URLs
        environment = os.getenv("ENVIRONMENT", "development").lower()
        production_domain = os.getenv("PRODUCTION_DOMAIN", "ai.factorialsystems.io")

        if environment == "production" or environment == "prod":
            # Production URLs
            backend_url = f"https://{production_domain}"
            chat_service_url = f"https://{production_domain}"
        else:
            # Development URLs (fallback to existing behavior)
            backend_url = os.getenv("BACKEND_URL", "http://localhost:8001")
            chat_service_url = os.getenv("CHAT_SERVICE_URL", "http://localhost:8000")

        context = {
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "api_key": tenant_details.get("apiKey", ""),
            "logo_info": logo_info,
            "colors": colors,
            "widget_id": f"factorial-chat-{tenant_id}",
            "backend_url": backend_url,
            "chat_service_url": chat_service_url,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            # Settings-based customization
            "hover_text": tenant_settings.get("hover_text", "Chat with us!"),
            "welcome_message": tenant_settings.get("welcome_message", "Hello! How can I help you today?"),
            "chat_window_title": tenant_settings.get("chat_window_title", "Chat Support"),
            "has_custom_logo": logo_info.get("is_custom", False),
            # Environment info for debugging
            "environment": environment,
            "production_domain": production_domain
        }
        
        return {
            "chat-widget.js": self._generate_javascript(context),
            "chat-widget.css": self._generate_css(context),
            "chat-widget.html": self._generate_html(context),
            "integration-guide.html": self._generate_integration_guide(context)
        }
    

    def _get_colors(self, tenant_settings: Dict[str, Any]) -> Dict[str, str]:
        """Get colors with tenant customization applied"""
        colors = self.colors.copy()
        
        # Override with tenant settings if available
        if tenant_settings.get("primary_color"):
            colors["primary"] = tenant_settings["primary_color"]
        if tenant_settings.get("secondary_color"):
            colors["secondary"] = tenant_settings["secondary_color"]
            
        return colors
    
    def _generate_chat_initials(self, company_name: str) -> str:
        """Generate 1-2 character initials from company name"""
        if not company_name or company_name.strip() == "" or company_name == "Unknown":
            return "CB"  # ChatBot fallback
        
        words = company_name.strip().split()
        initials = ""
        
        # Take first letter of first word (always)
        initials += words[0][0] if words and words[0] else "C"
        
        # If there are multiple words, take first letter of second word
        if len(words) > 1 and words[1]:
            initials += words[1][0]
        # If single word and long enough, take second character
        elif len(words) == 1 and len(words[0]) > 1:
            initials += words[0][1]
        else:
            initials += "B"  # Default second character
            
        return initials.upper()[:2]  # Ensure max 2 characters and uppercase
    
    def _get_logo_info(self, tenant_settings: Dict[str, Any] = None, tenant_name: str = "Unknown") -> Dict[str, Any]:
        """Get logo information from OAuth2 server settings or generate initials"""
        # Check if chatLogo info is provided in settings from OAuth2 server
        if tenant_settings and "chatLogo" in tenant_settings:
            chat_logo = tenant_settings["chatLogo"]
            if chat_logo.get("type") == "url" and chat_logo.get("url"):
                return {
                    "type": "url",
                    "source": chat_logo["url"],
                    "is_custom": True,
                    "initials": None
                }
            elif chat_logo.get("type") == "initials":
                return {
                    "type": "initials",
                    "source": None,
                    "is_custom": False,
                    "initials": chat_logo.get("initials", self._generate_chat_initials(tenant_name))
                }
        
        # Try to get custom company logo from OAuth2 server public endpoint
        if hasattr(self, '_tenant_id'):
            try:
                oauth2_server_url = os.getenv("AUTHORIZATION_SERVER_URL", "http://localhost:9000")
                public_logo_url = f"{oauth2_server_url}/api/v1/tenants/public/logos/{self._tenant_id}"
                
                # Check if the logo exists by making a HEAD request
                import requests
                try:
                    response = requests.head(public_logo_url, timeout=3)
                    if response.status_code == 200:
                        return {
                            "type": "url",
                            "source": public_logo_url,
                            "is_custom": True,
                            "initials": None
                        }
                except requests.exceptions.RequestException:
                    pass  # Fall through to initials
            except Exception:
                pass  # Fall through to initials
        
        # Use initials as fallback
        initials = self._generate_chat_initials(tenant_name)
        return {
            "type": "initials",
            "source": None,
            "is_custom": False,
            "initials": initials
        }
    
    def _generate_javascript(self, context: Dict[str, Any]) -> str:
        """Generate the main chat widget JavaScript"""
        js_template = """
(function() {
    'use strict';
    
    // Configuration
    const CONFIG = {
        tenantId: '{{ tenant_id }}',
        tenantName: '{{ tenant_name }}',
        apiKey: '{{ api_key }}',
        backendUrl: '{{ backend_url }}',
        chatServiceUrl: '{{ chat_service_url }}',
        widgetId: '{{ widget_id }}',
        colors: {
            primary: '{{ colors.primary }}',
            secondary: '{{ colors.secondary }}',
            accent: '{{ colors.accent }}',
            white: '{{ colors.white }}',
            gray: '{{ colors.gray }}',
            darkGray: '{{ colors.dark_gray }}',
            lightGray: '{{ colors.light_gray }}'
        },
        // Logo configuration
        logo: {
            type: '{{ logo_info.type }}',
            source: {% if logo_info.source %}'{{ logo_info.source }}'{% else %}null{% endif %},
            initials: {% if logo_info.initials %}'{{ logo_info.initials }}'{% else %}null{% endif %},
            isCustom: {{ 'true' if logo_info.is_custom else 'false' }}
        },
        // Customizable text
        hoverText: '{{ hover_text }}',
        welcomeMessage: '{{ welcome_message }}',
        chatWindowTitle: '{{ chat_window_title }}'
    };
    
    // Chat Widget Class
    class FactorialChatWidget {
        constructor() {
            this.isOpen = false;
            this.socket = null;
            this.messages = [];
            this.isConnected = false;
            this.chatContainer = null;
            this.messagesContainer = null;
            this.inputField = null;
            
            this.init();
        }
        
        init() {
            this.injectCSS();
            this.createWidget();
            this.attachEventListeners();
        }
        
        injectCSS() {
            if (document.getElementById('factorial-chat-css')) return;
            
            const style = document.createElement('style');
            style.id = 'factorial-chat-css';
            style.textContent = this.getCSS();
            document.head.appendChild(style);
        }
        
        getCSS() {
            return `
                .factorial-chat-widget {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    z-index: 999999;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                }
                
                .factorial-chat-button {
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    background: linear-gradient(45deg, ${CONFIG.colors.primary}, ${CONFIG.colors.secondary});
                    border: none;
                    cursor: pointer;
                    box-shadow: 0 4px 12px rgba(93, 62, 193, 0.3);
                    transition: all 0.3s ease;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    position: relative;
                }
                
                .factorial-chat-button:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(93, 62, 193, 0.4);
                }
                
                .factorial-chat-button-icon {
                    width: 24px;
                    height: 24px;
                    fill: ${CONFIG.colors.white};
                }
                
                .factorial-chat-button-logo {
                    width: 36px;
                    height: 36px;
                    border-radius: 50%;
                    object-fit: cover;
                    object-position: center;
                }
                
                .factorial-chat-button-initials {
                    width: 36px;
                    height: 36px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, ${CONFIG.colors.primary}, ${CONFIG.colors.secondary});
                    color: ${CONFIG.colors.white};
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 14px;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    transition: transform 0.3s ease;
                }
                
                .factorial-chat-button:hover .factorial-chat-button-initials {
                    transform: scale(1.1);
                }
                
                .factorial-chat-window {
                    position: fixed;
                    bottom: 100px;
                    right: 20px;
                    width: 380px;
                    height: 500px;
                    background: ${CONFIG.colors.white};
                    border-radius: 12px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
                    display: none;
                    flex-direction: column;
                    overflow: hidden;
                    z-index: 999998;
                }
                
                .factorial-chat-window.open {
                    display: flex;
                    animation: slideUp 0.3s ease;
                }
                
                @keyframes slideUp {
                    from { transform: translateY(20px); opacity: 0; }
                    to { transform: translateY(0); opacity: 1; }
                }
                
                .factorial-chat-header {
                    background: linear-gradient(135deg, ${CONFIG.colors.primary}, ${CONFIG.colors.secondary});
                    color: ${CONFIG.colors.white};
                    padding: 20px;
                    text-align: center;
                    position: relative;
                }
                
                .factorial-chat-close {
                    position: absolute;
                    top: 15px;
                    right: 15px;
                    background: none;
                    border: none;
                    color: ${CONFIG.colors.white};
                    font-size: 20px;
                    cursor: pointer;
                    opacity: 0.8;
                    transition: opacity 0.2s;
                }
                
                .factorial-chat-close:hover {
                    opacity: 1;
                }
                
                .factorial-chat-title {
                    font-size: 18px;
                    font-weight: 600;
                    margin: 0;
                }
                
                
                .factorial-chat-messages {
                    flex: 1;
                    padding: 20px;
                    overflow-y: auto;
                    background: ${CONFIG.colors.gray};
                }
                
                .factorial-chat-message {
                    margin-bottom: 15px;
                    display: flex;
                    align-items: flex-start;
                }
                
                .factorial-chat-message.user {
                    justify-content: flex-end;
                }
                
                .factorial-chat-message-content {
                    max-width: 70%;
                    padding: 12px 16px;
                    border-radius: 18px;
                    font-size: 14px;
                    line-height: 1.4;
                }
                
                .factorial-chat-message.user .factorial-chat-message-content {
                    background: ${CONFIG.colors.primary};
                    color: ${CONFIG.colors.white};
                    border-bottom-right-radius: 4px;
                }
                
                .factorial-chat-message.bot .factorial-chat-message-content {
                    background: ${CONFIG.colors.white};
                    color: ${CONFIG.colors.darkGray};
                    border: 1px solid ${CONFIG.colors.lightGray};
                    border-bottom-left-radius: 4px;
                }
                
                .factorial-chat-input-container {
                    padding: 20px;
                    border-top: 1px solid ${CONFIG.colors.lightGray};
                    display: flex;
                    gap: 10px;
                }
                
                .factorial-chat-input {
                    flex: 1;
                    padding: 12px 16px;
                    border: 1px solid ${CONFIG.colors.lightGray};
                    border-radius: 25px;
                    outline: none;
                    font-size: 14px;
                    transition: border-color 0.2s;
                }
                
                .factorial-chat-input:focus {
                    border-color: ${CONFIG.colors.primary};
                }
                
                .factorial-chat-send {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: ${CONFIG.colors.accent};
                    border: none;
                    color: ${CONFIG.colors.white};
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: background-color 0.2s;
                }
                
                .factorial-chat-send:hover {
                    background: #2ea049;
                }
                
                .factorial-chat-send:disabled {
                    background: ${CONFIG.colors.lightGray};
                    cursor: not-allowed;
                }
                
                .factorial-chat-footer {
                    padding: 12px 20px;
                    background: ${CONFIG.colors.white};
                    border-top: 1px solid ${CONFIG.colors.lightGray};
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    font-size: 12px;
                    color: ${CONFIG.colors.darkGray};
                }
                
                .factorial-chat-logo {
                    height: 20px;
                    width: auto;
                }
                
                .factorial-chat-logo-text {
                    font-weight: bold;
                    color: ${CONFIG.colors.primary};
                    margin-left: 4px;
                }
                
                .factorial-status-indicator {
                    position: absolute;
                    top: -2px;
                    right: -2px;
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    background: ${CONFIG.colors.accent};
                    border: 2px solid ${CONFIG.colors.white};
                }
                
                .factorial-status-indicator.disconnected {
                    background: #ff4444;
                }
                
                .factorial-typing-indicator {
                    display: flex;
                    align-items: center;
                    gap: 4px;
                    padding: 12px 16px;
                    color: ${CONFIG.colors.darkGray};
                    font-style: italic;
                    font-size: 13px;
                }
                
                .factorial-typing-dots {
                    display: flex;
                    gap: 2px;
                }
                
                .factorial-typing-dots span {
                    width: 4px;
                    height: 4px;
                    border-radius: 50%;
                    background: ${CONFIG.colors.primary};
                    animation: typing 1.4s infinite;
                }
                
                .factorial-typing-dots span:nth-child(2) {
                    animation-delay: 0.2s;
                }
                
                .factorial-typing-dots span:nth-child(3) {
                    animation-delay: 0.4s;
                }
                
                @keyframes typing {
                    0%, 60%, 100% { opacity: 0.3; }
                    30% { opacity: 1; }
                }
                
                @media (max-width: 480px) {
                    .factorial-chat-window {
                        width: calc(100vw - 40px);
                        height: calc(100vh - 140px);
                        bottom: 100px;
                        right: 20px;
                        left: 20px;
                    }
                }
            `;
        }
        
        createWidget() {
            const widgetContainer = document.createElement('div');
            widgetContainer.className = 'factorial-chat-widget';
            widgetContainer.id = CONFIG.widgetId;
            
            widgetContainer.innerHTML = `
                <button class="factorial-chat-button" id="factorial-chat-toggle" title="${CONFIG.hoverText}">
                    {% if logo_info.type == 'url' and logo_info.source %}
                    <img src="{{ logo_info.source }}" alt="Chat" class="factorial-chat-button-logo">
                    {% elif logo_info.type == 'initials' and logo_info.initials %}
                    <div class="factorial-chat-button-initials">{{ logo_info.initials }}</div>
                    {% else %}
                    <svg viewBox="0 0 24 24" class="factorial-chat-button-icon">
                        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
                    </svg>
                    {% endif %}
                    <div class="factorial-status-indicator" id="factorial-status"></div>
                </button>
                
                <div class="factorial-chat-window" id="factorial-chat-window">
                    <div class="factorial-chat-header">
                        <button class="factorial-chat-close" id="factorial-chat-close">&times;</button>
                        <h3 class="factorial-chat-title">${CONFIG.chatWindowTitle}</h3>
                    </div>
                    
                    <div class="factorial-chat-messages" id="factorial-chat-messages">
                        <div class="factorial-chat-message bot">
                            <div class="factorial-chat-message-content">
                                ${CONFIG.welcomeMessage}
                            </div>
                        </div>
                    </div>
                    
                    <div class="factorial-chat-input-container">
                        <input type="text" class="factorial-chat-input" id="factorial-chat-input" placeholder="Type your message..." maxlength="1000">
                        <button class="factorial-chat-send" id="factorial-chat-send" disabled>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                            </svg>
                        </button>
                    </div>
                    
                    <div class="factorial-chat-footer">
                        <span>Powered by</span>
                        <img src="{{ backend_url }}/api/v1/widget/static/chatcraft-logo2.png" alt="ChatCraft" class="factorial-chat-logo">
                    </div>
                </div>
            `;
            
            document.body.appendChild(widgetContainer);
            
            this.chatContainer = document.getElementById('factorial-chat-window');
            this.messagesContainer = document.getElementById('factorial-chat-messages');
            this.inputField = document.getElementById('factorial-chat-input');
        }
        
        attachEventListeners() {
            const toggleButton = document.getElementById('factorial-chat-toggle');
            const closeButton = document.getElementById('factorial-chat-close');
            const sendButton = document.getElementById('factorial-chat-send');
            const inputField = this.inputField;
            
            toggleButton.addEventListener('click', () => this.toggleChat());
            closeButton.addEventListener('click', () => this.closeChat());
            sendButton.addEventListener('click', () => this.sendMessage());
            
            inputField.addEventListener('input', (e) => {
                sendButton.disabled = !e.target.value.trim();
            });
            
            inputField.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey && e.target.value.trim()) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        
        toggleChat() {
            if (this.isOpen) {
                this.closeChat();
            } else {
                this.openChat();
            }
        }
        
        openChat() {
            this.isOpen = true;
            this.chatContainer.classList.add('open');
            this.inputField.focus();
            
            if (!this.isConnected) {
                this.connectWebSocket();
            }
        }
        
        closeChat() {
            this.isOpen = false;
            this.chatContainer.classList.remove('open');
        }
        
        connectWebSocket() {
            // Convert HTTP/HTTPS URLs to WebSocket URLs
            let wsUrl = CONFIG.chatServiceUrl.replace('http://', 'ws://').replace('https://', 'wss://');

            // For production domains, ensure we use the direct /ws/chat path
            // since nginx proxies /ws/chat directly to the chat service
            const wsEndpoint = `${wsUrl}/ws/chat?api_key=${CONFIG.apiKey}`;
            
            try {
                this.socket = new WebSocket(wsEndpoint);
                
                this.socket.onopen = () => {
                    this.isConnected = true;
                    this.updateConnectionStatus(true);
                };
                
                this.socket.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    if (data.type === 'message' && data.role === 'assistant') {
                        this.addMessage('bot', data.content);
                        this.hideTypingIndicator();
                        this.enableSendButton();
                    } else if (data.type === 'connection') {
                        console.log('Connected to chat service:', data.message);
                    } else if (data.type === 'error') {
                        console.error('Chat service error:', data.message);
                        this.addMessage('bot', 'Sorry, I encountered an error. Please try again later.');
                        this.hideTypingIndicator();
                        this.enableSendButton();
                    }
                };
                
                this.socket.onclose = () => {
                    this.isConnected = false;
                    this.updateConnectionStatus(false);
                    this.hideTypingIndicator();
                };
                
                this.socket.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    this.isConnected = false;
                    this.updateConnectionStatus(false);
                    this.addMessage('bot', 'Sorry, I encountered an error. Please try again later.');
                };
                
            } catch (error) {
                console.error('Failed to connect to chat service:', error);
                this.addMessage('bot', 'Unable to connect to chat service. Please check your internet connection.');
            }
        }
        
        updateConnectionStatus(connected) {
            const statusIndicator = document.getElementById('factorial-status');
            if (connected) {
                statusIndicator.classList.remove('disconnected');
            } else {
                statusIndicator.classList.add('disconnected');
            }
        }
        
        sendMessage() {
            const message = this.inputField.value.trim();
            if (!message || !this.isConnected) return;
            
            this.addMessage('user', message);
            this.inputField.value = '';
            document.getElementById('factorial-chat-send').disabled = true;
            
            this.showTypingIndicator();
            
            // Send message via WebSocket
            this.socket.send(JSON.stringify({
                type: 'message',
                message: message
            }));
        }
        
        addMessage(sender, content) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `factorial-chat-message ${sender}`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'factorial-chat-message-content';
            contentDiv.textContent = content;
            
            messageDiv.appendChild(contentDiv);
            this.messagesContainer.appendChild(messageDiv);
            
            // Auto-scroll to bottom
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }
        
        showTypingIndicator() {
            const existingIndicator = document.getElementById('factorial-typing-indicator');
            if (existingIndicator) return;
            
            const indicatorDiv = document.createElement('div');
            indicatorDiv.className = 'factorial-chat-message bot';
            indicatorDiv.id = 'factorial-typing-indicator';
            
            indicatorDiv.innerHTML = `
                <div class="factorial-typing-indicator">
                    <span>AI is typing</span>
                    <div class="factorial-typing-dots">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            `;
            
            this.messagesContainer.appendChild(indicatorDiv);
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }
        
        hideTypingIndicator() {
            const indicator = document.getElementById('factorial-typing-indicator');
            if (indicator) {
                indicator.remove();
            }
        }
        
        enableSendButton() {
            const sendButton = document.getElementById('factorial-chat-send');
            if (sendButton) {
                sendButton.disabled = false;
            }
        }
    }
    
    // Initialize widget when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            new FactorialChatWidget();
        });
    } else {
        new FactorialChatWidget();
    }
})();
"""
        template = Template(js_template)
        return template.render(**context)
    
    def _generate_css(self, context: Dict[str, Any]) -> str:
        """Generate additional CSS file (optional)"""
        css_template = """
/* Additional CSS customizations for FactorialBot Chat Widget */
/* This file is optional and can be used for advanced customizations */

.factorial-chat-widget {
    /* Custom positioning can be applied here */
}

/* Custom animations */
@keyframes factorial-bounce {
    0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
    40% { transform: translateY(-10px); }
    60% { transform: translateY(-5px); }
}

.factorial-chat-button:active {
    animation: factorial-bounce 0.6s;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
    .factorial-chat-window {
        background: #2a2a2a;
        color: #ffffff;
    }
    
    .factorial-chat-messages {
        background: #1a1a1a;
    }
    
    .factorial-chat-message.bot .factorial-chat-message-content {
        background: #3a3a3a;
        color: #ffffff;
        border-color: #555555;
    }
}

/* Custom scrollbar */
.factorial-chat-messages::-webkit-scrollbar {
    width: 6px;
}

.factorial-chat-messages::-webkit-scrollbar-track {
    background: {{ colors.light_gray }};
}

.factorial-chat-messages::-webkit-scrollbar-thumb {
    background: {{ colors.primary }};
    border-radius: 3px;
}

.factorial-chat-messages::-webkit-scrollbar-thumb:hover {
    background: {{ colors.secondary }};
}
"""
        template = Template(css_template)
        return template.render(**context)
    
    def _generate_html(self, context: Dict[str, Any]) -> str:
        """Generate HTML template for testing"""
        html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FactorialBot Chat Widget - {{ tenant_name }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, {{ colors.primary }}22, {{ colors.accent }}22);
            min-height: 100vh;
        }
        
        .demo-container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        }
        
        h1 {
            color: {{ colors.primary }};
            text-align: center;
            margin-bottom: 30px;
        }
        
        .info-card {
            background: {{ colors.gray }};
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid {{ colors.accent }};
        }
        
        .integration-code {
            background: #1e1e1e;
            color: #f8f8f2;
            padding: 20px;
            border-radius: 8px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 14px;
            overflow-x: auto;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="demo-container">
        <h1>🤖 FactorialBot Chat Widget Demo</h1>
        
        <div class="info-card">
            <h3>Tenant Information</h3>
            <p><strong>Organization:</strong> {{ tenant_name }}</p>
            <p><strong>Widget ID:</strong> {{ widget_id }}</p>
            <p><strong>Status:</strong> <span style="color: {{ colors.accent }};">✓ Active</span></p>
        </div>
        
        <div class="info-card">
            <h3>Integration Instructions</h3>
            <p>To integrate this chat widget into your website, add the following script tag just before the closing <code>&lt;/body&gt;</code> tag:</p>
            
            <div class="integration-code">
&lt;!-- FactorialBot Chat Widget --&gt;
&lt;script src="https://your-domain.com/path/to/chat-widget.js"&gt;&lt;/script&gt;
            </div>
            
            <p>Or use the inline version:</p>
            
            <div class="integration-code">
&lt;!-- FactorialBot Chat Widget (Inline) --&gt;
&lt;script&gt;
    // Paste the contents of chat-widget.js here
&lt;/script&gt;
            </div>
        </div>
        
        <div class="info-card">
            <h3>Features</h3>
            <ul>
                <li>✨ Real-time chat with AI assistance</li>
                <li>📱 Mobile-responsive design</li>
                <li>🎨 Customizable colors and branding</li>
                <li>🔒 Secure WebSocket connection</li>
                <li>⚡ Fast loading and lightweight</li>
                <li>🌙 Dark mode support</li>
            </ul>
        </div>
        
        <p style="text-align: center; margin-top: 40px; color: {{ colors.dark_gray }};">
            Look for the chat button in the bottom-right corner! 👉
        </p>
    </div>
    
    <!-- The actual chat widget will be loaded here -->
    <script>
        {{ widget_js_content }}
    </script>
</body>
</html>
"""
        context["widget_js_content"] = self._generate_javascript(context)
        template = Template(html_template)
        return template.render(**context)
    
    def _generate_integration_guide(self, context: Dict[str, Any]) -> str:
        """Generate integration guide HTML"""
        guide_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FactorialBot Integration Guide - {{ tenant_name }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f9f9f9;
        }
        
        .header {
            background: linear-gradient(135deg, {{ colors.primary }}, {{ colors.secondary }});
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            margin-bottom: 30px;
        }
        
        .section {
            background: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        .code-block {
            background: #1e1e1e;
            color: #f8f8f2;
            padding: 20px;
            border-radius: 8px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 14px;
            overflow-x: auto;
            margin: 15px 0;
        }
        
        .highlight {
            background: {{ colors.accent }}22;
            padding: 15px;
            border-left: 4px solid {{ colors.accent }};
            border-radius: 4px;
            margin: 15px 0;
        }
        
        .warning {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            color: #856404;
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
        }
        
        h1, h2, h3 { color: {{ colors.primary }}; }
        
        .step {
            counter-increment: step-counter;
            margin: 20px 0;
            padding: 20px;
            background: {{ colors.gray }};
            border-radius: 8px;
            position: relative;
        }
        
        .step::before {
            content: counter(step-counter);
            position: absolute;
            left: -10px;
            top: -10px;
            background: {{ colors.primary }};
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
        }
        
        .steps {
            counter-reset: step-counter;
        }
        
        .download-section {
            text-align: center;
            background: linear-gradient(135deg, {{ colors.primary }}11, {{ colors.accent }}11);
            padding: 30px;
            border-radius: 12px;
            margin: 30px 0;
        }
        
        .download-button {
            display: inline-block;
            padding: 12px 24px;
            background: {{ colors.primary }};
            color: white;
            text-decoration: none;
            border-radius: 6px;
            margin: 5px;
            transition: background 0.2s;
        }
        
        .download-button:hover {
            background: {{ colors.secondary }};
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 FactorialBot Chat Widget</h1>
        <h2>Integration Guide for {{ tenant_name }}</h2>
        <p>Get your AI-powered chat assistant up and running in minutes!</p>
    </div>
    
    <div class="section">
        <h2>📋 Quick Start</h2>
        <p>Follow these simple steps to add the FactorialBot chat widget to your website:</p>
        
        <div class="steps">
            <div class="step">
                <h3>Download the Widget Files</h3>
                <p>Download the generated widget files for your organization:</p>
                <div class="download-section">
                    <a href="/api/v1/widget/chat-widget.js" class="download-button" download>
                        📄 chat-widget.js
                    </a>
                    <a href="/api/v1/widget/chat-widget.css" class="download-button" download>
                        🎨 chat-widget.css
                    </a>
                    <a href="/api/v1/widget/chat-widget.html" class="download-button" download>
                        📋 demo.html
                    </a>
                </div>
            </div>
            
            <div class="step">
                <h3>Upload to Your Website</h3>
                <p>Upload the <code>chat-widget.js</code> file to your website's public directory (e.g., in a <code>/js/</code> or <code>/assets/</code> folder).</p>
            </div>
            
            <div class="step">
                <h3>Add the Script Tag</h3>
                <p>Add the following script tag just before the closing <code>&lt;/body&gt;</code> tag of your HTML pages:</p>
                
                <div class="code-block">
&lt;!-- FactorialBot Chat Widget --&gt;
&lt;script src="/path/to/chat-widget.js"&gt;&lt;/script&gt;
&lt;/body&gt;
&lt;/html&gt;
                </div>
            </div>
            
            <div class="step">
                <h3>Test the Integration</h3>
                <p>Refresh your website and look for the chat button in the bottom-right corner. Click it to test the chat functionality!</p>
            </div>
        </div>
    </div>
    
    <div class="section">
        <h2>⚡ Alternative: Inline Integration</h2>
        <p>For maximum control and to avoid external file dependencies, you can embed the widget code directly in your HTML:</p>
        
        <div class="code-block">
&lt;!-- FactorialBot Chat Widget (Inline) --&gt;
&lt;script&gt;
// Copy the entire contents of chat-widget.js and paste here
(function() {
    'use strict';
    // ... widget code ...
})();
&lt;/script&gt;
        </div>
        
        <div class="highlight">
            <strong>💡 Pro Tip:</strong> The inline method ensures the chat widget always loads, even if external scripts are blocked.
        </div>
    </div>
    
    <div class="section">
        <h2>🎨 Customization Options</h2>
        <p>The widget uses your organization's brand colors automatically:</p>
        <ul>
            <li><strong>Primary:</strong> <span style="color: {{ colors.primary }};">{{ colors.primary }}</span> (Purple)</li>
            <li><strong>Secondary:</strong> <span style="color: {{ colors.secondary }};">{{ colors.secondary }}</span> (Orange)</li>
            <li><strong>Accent:</strong> <span style="color: {{ colors.accent }};">{{ colors.accent }}</span> (Green)</li>
        </ul>
        
        <p>You can customize the widget's appearance by modifying the CSS variables in the JavaScript file or by overriding styles in your own CSS.</p>
    </div>
    
    <div class="section">
        <h2>🔧 Configuration</h2>
        <p>Your widget is pre-configured with the following settings:</p>
        
        <div class="code-block">
Tenant ID: {{ tenant_id }}
Organization: {{ tenant_name }}
API Key: {{ api_key[:8] }}...
Backend URL: {{ backend_url }}
Chat Service URL: {{ chat_service_url }}
        </div>
        
        <div class="warning">
            <strong>⚠️ Security Note:</strong> Your API key is embedded in the JavaScript file. While this is necessary for the widget to function, make sure to only use this widget on your own domains. Do not share the widget files publicly.
        </div>
    </div>
    
    <div class="section">
        <h2>📱 Features</h2>
        <ul>
            <li>✨ <strong>Real-time AI Chat:</strong> Instant responses powered by advanced AI</li>
            <li>📱 <strong>Mobile Responsive:</strong> Works perfectly on all devices</li>
            <li>🎨 <strong>Brand Integration:</strong> Uses your organization's colors</li>
            <li>🔒 <strong>Secure Connection:</strong> WebSocket encryption for safe communication</li>
            <li>⚡ <strong>Lightweight:</strong> Minimal impact on page load speed</li>
            <li>🌙 <strong>Dark Mode:</strong> Automatic dark mode support</li>
            <li>♿ <strong>Accessible:</strong> Screen reader compatible</li>
        </ul>
    </div>
    
    <div class="section">
        <h2>❓ Troubleshooting</h2>
        
        <h3>Chat button not appearing?</h3>
        <ul>
            <li>Check browser console for JavaScript errors</li>
            <li>Verify the script path is correct</li>
            <li>Ensure the script is loaded after the DOM</li>
        </ul>
        
        <h3>Chat not connecting?</h3>
        <ul>
            <li>Verify your API key is valid</li>
            <li>Check if WebSocket connections are blocked</li>
            <li>Confirm the chat service URL is accessible</li>
        </ul>
        
        <h3>Styling issues?</h3>
        <ul>
            <li>Check for CSS conflicts with existing styles</li>
            <li>The widget uses high z-index values (999999)</li>
            <li>All styles are prefixed with 'factorial-' to avoid conflicts</li>
        </ul>
    </div>
    
    <div class="section">
        <h2>📞 Support</h2>
        <p>Need help with the integration? Contact our support team:</p>
        <ul>
            <li>🌐 Visit: <a href="{{ backend_url }}" target="_blank">{{ backend_url }}</a></li>
            <li>📧 Email: support@factorialbot.com</li>
            <li>💬 Chat: Use the demo widget to test and get familiar with the interface</li>
        </ul>
    </div>
    
    <div style="text-align: center; margin-top: 50px; padding: 20px; color: #666;">
        <p>Generated on {{ generated_at }} UTC</p>
        <p>FactorialBot Widget v1.0 - Powered by AI</p>
    </div>
</body>
</html>
"""
        template = Template(guide_template)
        return template.render(**context)