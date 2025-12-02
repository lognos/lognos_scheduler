/**
 * Specific error types for better error handling and UX.
 */

export class ConversationNotFoundError extends Error {
    constructor(conversationId: string) {
        super(`Conversation ${conversationId} not found`);
        this.name = 'ConversationNotFoundError';
    }
}

export class ConversationLoadError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'ConversationLoadError';
    }
}

export class UnauthorizedConversationError extends Error {
    constructor() {
        super('You do not have permission to access this conversation');
        this.name = 'UnauthorizedConversationError';
    }
}

export class NetworkError extends Error {
    constructor(originalError?: Error) {
        super('Network error. Please check your connection.');
        this.name = 'NetworkError';
        if (originalError) {
            this.stack = originalError.stack;
        }
    }
}
