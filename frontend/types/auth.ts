export interface AuthUser {
    id: string
    email: string
    name?: string
    user_email: string
    user_name: string
    user_role: string
    user_cellphone?: string
    preferred_language?: string
    first_name?: string
}

export interface User {
    id: string
    user_email: string
    user_name: string
    user_role: string
    user_cellphone?: string
    preferred_language?: string
    created_at?: string
    first_name?: string
}
