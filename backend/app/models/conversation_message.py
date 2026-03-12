"""
Conversation Message model for storing chat history with AI agents.

This module defines the ConversationMessage model, which stores the conversation
history between users and AI agents. The model has a many-to-one relationship
with the User model, allowing users to have multiple conversation messages.

Key Features:
- Message role tracking (user/assistant)
- Agent type filtering (which agent handled the message)
- Image attachment support
- Warning tracking
- Timestamp tracking for conversation flow
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ConversationMessage(Base):
    """
    Conversation Message model storing chat history between users and AI agents.
    
    This model stores individual messages in conversations between users and AI agents.
    Each message entry represents either a user input or an agent response, with
    metadata about which agent handled the message. The model has a many-to-one
    relationship with User model.
    
    Attributes:
        id: Primary key, auto-incrementing integer
        user_id: Foreign key to User model (required)
        role: Message role - 'user' or 'assistant' (required)
        content: Message content/text (required)
        warnings: Warnings associated with the message (JSON string, nullable)
        image_path: Path to stored image file if message includes image (nullable)
        agent_type: Type of agent that handled/responded to the message (required)
        created_at: Timestamp when message was created
        
    Relationships:
        user: Many-to-one relationship with User model
        
    Agent Types:
        The agent_type field identifies which agent handled the message:
        - "physical-fitness": Physical Fitness Agent
        - "nutrition": Nutrition Agent
        - "mental-fitness": Mental Fitness Agent
        - "coordinator": Coordinator Agent (routes queries or creates holistic plans)
        
        This allows filtering conversation history by agent type, which is useful
        for providing context to agents about previous conversations.
        
    Message Roles:
        - "user": Message sent by the user (input/query)
        - "assistant": Message sent by the AI agent (response)
        
    Image Support:
        When a user sends an image (e.g., food photo for Nutrition Agent), the image
        is stored on disk and the path is stored in image_path. The image_path
        field allows retrieval of the image for display or further processing.
        
    Warnings Format:
        The warnings field stores warnings as JSON string array:
        ["Warning message 1", "Warning message 2"]
        
        Warnings can include:
        - Safety warnings (e.g., exercise conflicts with medical conditions)
        - Data quality warnings (e.g., incomplete information)
        - Service degradation warnings (e.g., fallback model used)
        
    Note:
        - Multiple conversation messages can exist per user (many-to-one relationship)
        - Messages are ordered by created_at timestamp for conversation flow
        - Agent type filtering allows agents to see relevant conversation history
        - Image support enables image-based interactions (e.g., food photo analysis)
        - Warnings help users understand limitations or issues with responses
    """
    __tablename__ = "conversation_messages"

    # Primary key - auto-incrementing integer
    # Indexed for fast lookups by ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to User model
    # Many-to-one relationship (each user can have multiple conversation messages)
    # Required field - cannot be null
    # Indexed for fast queries filtering by user
    # Cascade delete: if user is deleted, conversation messages are also deleted
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Message role - identifies who sent the message
    # Values: "user" (user input) or "assistant" (AI agent response)
    # Used to distinguish user queries from agent responses
    # Required field - cannot be null
    # Used for conversation flow reconstruction
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    
    # Message content - the actual text of the message
    # Format: Plain text containing the message content
    # For user messages: the user's query or input
    # For assistant messages: the agent's response
    # Required field - cannot be null
    # Text type allows for long messages
    content = Column(Text, nullable=False)
    
    # Warnings - warnings associated with the message
    # Format: JSON string containing array of warning messages
    # Example: ["Exercise may conflict with knee injury", "Using fallback model"]
    # Used to inform users about limitations, safety concerns, or service issues
    # Nullable to allow messages without warnings
    warnings = Column(Text, nullable=True)  # JSON string for warnings array
    
    # Image path - path to stored image file if message includes an image
    # Format: Relative path from uploads directory (e.g., "images/user123_food_photo.jpg")
    # Used for image-based interactions (e.g., food photo analysis by Nutrition Agent)
    # Images are stored on disk and served statically via /uploads endpoint
    # Nullable to allow text-only messages
    image_path = Column(String, nullable=True)  # Path to stored image file
    
    # Agent type - identifies which agent handled/responded to the message
    # Values: "physical-fitness", "nutrition", "mental-fitness", "coordinator"
    # Used for filtering conversation history by agent type
    # Allows agents to see relevant conversation context
    # Defaults to "coordinator" for backward compatibility
    # Required field - cannot be null
    # Indexed for fast queries filtering by agent type
    agent_type = Column(String, nullable=False, default='coordinator')  # 'physical-fitness', 'nutrition', 'mental-fitness', 'coordinator'
    
    # Message creation timestamp
    # Automatically set to current time when message is created
    # Timezone-aware DateTime for accurate time tracking
    # Used for ordering messages in conversation flow
    # No updated_at field - messages are immutable once created
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to User model
    # Many-to-one relationship (each user can have multiple conversation messages)
    # Access via: conversation_message.user (returns User object)
    # Back-populates with User.conversation_messages (returns list of ConversationMessage objects)
    user = relationship("User", back_populates="conversation_messages")

