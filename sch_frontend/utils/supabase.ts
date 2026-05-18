import { createClient, SupabaseClient } from '@supabase/supabase-js'

// Lazy initialization to avoid build-time errors
// Supabase client is only created when actually used
let supabaseInstance: SupabaseClient | null = null

function createSupabaseClient(): SupabaseClient {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
    const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

    if (!supabaseUrl || !supabaseAnonKey) {
        throw new Error('Missing Supabase environment variables')
    }

    return createClient(supabaseUrl, supabaseAnonKey)
}

export function getSupabase(): SupabaseClient {
    if (!supabaseInstance) {
        supabaseInstance = createSupabaseClient()
    }
    return supabaseInstance
}

// Export as getter for backward compatibility
// This will throw at runtime if env vars are missing, not at build time
export const supabase = {
    get auth() {
        return getSupabase().auth
    },
    get from() {
        return getSupabase().from.bind(getSupabase())
    },
    get storage() {
        return getSupabase().storage
    },
    get functions() {
        return getSupabase().functions
    },
    get realtime() {
        return getSupabase().realtime
    },
    get rpc() {
        return getSupabase().rpc.bind(getSupabase())
    },
    get channel() {
        return getSupabase().channel.bind(getSupabase())
    },
    get removeChannel() {
        return getSupabase().removeChannel.bind(getSupabase())
    },
    get removeAllChannels() {
        return getSupabase().removeAllChannels.bind(getSupabase())
    },
    get getChannels() {
        return getSupabase().getChannels.bind(getSupabase())
    }
}
