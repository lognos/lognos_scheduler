export interface UserPreferences {
    theme: 'light' | 'dark' | 'system';
    language: string;
    notifications_enabled: boolean;
    default_project_id?: string;
    extra_settings?: Record<string, any>;
}

export interface UserContextType {
    user_id: string;
    email: string;
    full_name?: string;
    first_name?: string;
    roles: string[];
    preferences: UserPreferences;
    active_project_id?: string;
    display_name: string;
}
