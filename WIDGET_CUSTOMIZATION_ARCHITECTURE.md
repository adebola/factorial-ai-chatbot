# Chat Widget Customization Architecture

## 🎨 Customization Features

### Visual Customization Options:
- **Colors**: Primary, secondary, background, text colors for chat window and floating button
- **Fonts**: Font family, sizes for different text elements
- **Branding Logo**: Custom company logo in chat header
- **Floating Icon**: Custom icon for the chat button
- **Chatbot Avatar**: Custom avatar image for AI responses
- **Chat Window Title**: Custom header text
- **Chatbot Name**: Custom name displayed in conversations

## 📋 Implementation Plan

### Phase 1: Database Schema Enhancement
```sql
-- New table for widget customization settings
CREATE TABLE widget_customizations (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    
    -- Colors (hex codes)
    primary_color VARCHAR(7) DEFAULT '#5D3EC1',
    secondary_color VARCHAR(7) DEFAULT '#C15D3E', 
    background_color VARCHAR(7) DEFAULT '#FFFFFF',
    text_color VARCHAR(7) DEFAULT '#333333',
    button_color VARCHAR(7) DEFAULT '#5D3EC1',
    
    -- Typography
    font_family VARCHAR(100) DEFAULT 'Inter, sans-serif',
    font_size_small VARCHAR(10) DEFAULT '12px',
    font_size_medium VARCHAR(10) DEFAULT '14px',
    font_size_large VARCHAR(10) DEFAULT '16px',
    
    -- Branding
    company_logo_url VARCHAR(500),
    chatbot_avatar_url VARCHAR(500),
    floating_icon_url VARCHAR(500),
    
    -- Text Content
    chat_window_title VARCHAR(100) DEFAULT 'Chat Support',
    chatbot_name VARCHAR(50) DEFAULT 'Assistant',
    welcome_message TEXT DEFAULT 'Hello! How can I help you today?',
    
    -- Layout Settings
    chat_position VARCHAR(20) DEFAULT 'bottom-right', -- bottom-right, bottom-left, etc.
    chat_width VARCHAR(10) DEFAULT '350px',
    chat_height VARCHAR(10) DEFAULT '500px',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Phase 2: API Endpoints

**Widget Customization Management:**
- `GET /api/v1/widget/customization` - Get current settings
- `PUT /api/v1/widget/customization` - Update settings
- `POST /api/v1/widget/upload-logo` - Upload company logo
- `POST /api/v1/widget/upload-avatar` - Upload chatbot avatar
- `POST /api/v1/widget/upload-icon` - Upload floating icon
- `GET /api/v1/widget/preview` - Generate preview with custom settings

### Phase 3: Enhanced Widget Generation

**Dynamic CSS Generation:**
```python
def generate_custom_css(customization: WidgetCustomization) -> str:
    return f"""
    :root {{
        --chat-primary: {customization.primary_color};
        --chat-secondary: {customization.secondary_color};
        --chat-bg: {customization.background_color};
        --chat-text: {customization.text_color};
        --chat-font: {customization.font_family};
        --chat-width: {customization.chat_width};
        --chat-height: {customization.chat_height};
    }}
    
    .factorialbot-chat-container {{
        font-family: var(--chat-font);
        width: var(--chat-width);
        height: var(--chat-height);
        background: var(--chat-bg);
        color: var(--chat-text);
    }}
    
    .factorialbot-floating-button {{
        background: {customization.button_color};
        background-image: url('{customization.floating_icon_url or 'default-icon.svg'}');
    }}
    """
```

**JavaScript Widget Updates:**
```javascript
class FactorialBotWidget {
    constructor(config) {
        this.tenantId = config.tenantId;
        this.apiUrl = config.apiUrl;
        this.customization = config.customization || {};
        this.initializeWidget();
    }
    
    async loadCustomization() {
        const response = await fetch(`${this.apiUrl}/widget/customization`);
        this.customization = await response.json();
        this.applyCustomization();
    }
    
    applyCustomization() {
        // Apply colors, fonts, images dynamically
        const root = document.documentElement;
        root.style.setProperty('--chat-primary', this.customization.primary_color);
        root.style.setProperty('--chat-font', this.customization.font_family);
        
        // Update text content
        this.chatTitle.textContent = this.customization.chat_window_title;
        this.welcomeMessage = this.customization.welcome_message;
    }
}
```

### Phase 4: File Storage & Management

**Image Upload Service:**
```python
class WidgetImageService:
    def __init__(self):
        self.storage_service = StorageService()
    
    async def upload_logo(self, tenant_id: str, file: UploadFile) -> str:
        # Validate image format and size
        # Resize/optimize image
        # Store in MinIO with tenant prefix
        filename = f"widget-assets/{tenant_id}/logo.{file.extension}"
        url = await self.storage_service.upload_file(file, filename)
        return url
    
    async def upload_avatar(self, tenant_id: str, file: UploadFile) -> str:
        # Similar process for avatars
        pass
```

### Phase 5: Preview & Validation System

**Real-time Preview:**
- Live preview API that generates widget with current settings
- Validation for color contrast, image sizes, text lengths
- CSS/JS generation with fallbacks for missing customizations

## 🛠️ Technical Implementation Details

### Database Model (SQLAlchemy):
```python
class WidgetCustomization(Base):
    __tablename__ = "widget_customizations"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    
    # Colors
    primary_color = Column(String(7), default="#5D3EC1")
    secondary_color = Column(String(7), default="#C15D3E")
    background_color = Column(String(7), default="#FFFFFF")
    text_color = Column(String(7), default="#333333")
    button_color = Column(String(7), default="#5D3EC1")
    
    # Typography
    font_family = Column(String(100), default="Inter, sans-serif")
    font_size_small = Column(String(10), default="12px")
    font_size_medium = Column(String(10), default="14px")
    font_size_large = Column(String(10), default="16px")
    
    # Assets
    company_logo_url = Column(String(500))
    chatbot_avatar_url = Column(String(500))
    floating_icon_url = Column(String(500))
    
    # Content
    chat_window_title = Column(String(100), default="Chat Support")
    chatbot_name = Column(String(50), default="Assistant")
    welcome_message = Column(Text, default="Hello! How can I help you today?")
    
    # Layout
    chat_position = Column(String(20), default="bottom-right")
    chat_width = Column(String(10), default="350px")
    chat_height = Column(String(10), default="500px")
```

### Service Integration:
```python
class WidgetCustomizationService:
    def __init__(self, db: Session):
        self.db = db
        self.image_service = WidgetImageService()
        
    def get_customization(self, tenant_id: str) -> WidgetCustomization:
        customization = self.db.query(WidgetCustomization).filter(
            WidgetCustomization.tenant_id == tenant_id
        ).first()
        
        if not customization:
            # Create default customization
            customization = self.create_default_customization(tenant_id)
            
        return customization
    
    def update_customization(self, tenant_id: str, updates: dict) -> WidgetCustomization:
        customization = self.get_customization(tenant_id)
        
        for key, value in updates.items():
            if hasattr(customization, key):
                setattr(customization, key, value)
        
        customization.updated_at = datetime.utcnow()
        self.db.commit()
        return customization
```

## 🎯 Benefits

1. **Brand Consistency**: Customers can match widget to their brand identity
2. **User Experience**: Personalized chat experience improves engagement
3. **Professional Appearance**: Custom styling makes the widget look native to their site
4. **Competitive Advantage**: Advanced customization as a premium feature
5. **Customer Satisfaction**: Full control over chat widget appearance

## 📈 Rollout Strategy

1. **Phase 1**: Basic color and text customization (Week 1-2)
2. **Phase 2**: Font and layout options (Week 3)
3. **Phase 3**: Image uploads and branding (Week 4)
4. **Phase 4**: Advanced positioning and sizing (Week 5)
5. **Phase 5**: Preview system and validation (Week 6)

This plan provides comprehensive widget customization while maintaining system performance and security.

## 🔧 Implementation Priority

### High Priority (MVP):
- Basic color customization (primary, secondary, background, text)
- Chat window title and chatbot name
- Welcome message customization
- Company logo upload

### Medium Priority:
- Font family and size options
- Chatbot avatar upload
- Floating button icon customization
- Chat position (bottom-right, bottom-left)

### Low Priority (Advanced Features):
- Custom CSS injection
- Animation preferences
- Sound settings
- Advanced layout controls
- Multi-language support for UI elements

## 🚀 Technical Considerations

### Performance:
- Cache generated CSS/JS files
- Optimize image uploads with automatic resizing
- Use CDN for serving widget assets
- Implement lazy loading for customization data

### Security:
- Validate all uploaded images (type, size, malware scanning)
- Sanitize all text inputs to prevent XSS
- Implement rate limiting on upload endpoints
- Use secure file storage with proper access controls

### Scalability:
- Store generated widgets in cache/CDN
- Use background jobs for image processing
- Implement versioning for widget updates
- Consider multi-region asset distribution