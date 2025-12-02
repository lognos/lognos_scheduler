/**
 * Loading skeleton for conversation list items.
 */
export function ConversationSkeleton() {
    return (
        <div className="px-4 py-3 animate-pulse">
            <div className="h-4 bg-gray-700 rounded w-3/4 mb-2"></div>
            <div className="h-3 bg-gray-700 rounded w-1/2"></div>
        </div>
    );
}
