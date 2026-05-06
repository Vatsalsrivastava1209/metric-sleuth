'use server'

import { createClient } from '@/utils/supabase/server'
import crypto from 'crypto'

export async function generateApiKey(formData: FormData) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  
  if (!user) {
    throw new Error("Unauthorized")
  }
  
  const keyName = formData.get('name') as string || 'New API Key'
  
  // 1. Generate a secure random string (32 bytes)
  const rawSecret = crypto.randomBytes(32).toString('hex')
  
  // 2. Format the persistent key exactly like Stripe (sk_live_...)
  const prefix = 'sk_live_'
  const plainTextKey = `${prefix}${rawSecret}`
  
  // 3. Hash the key for secure DB storage (SHA-256)
  const hashedKey = crypto.createHash('sha256').update(plainTextKey).digest('hex')
  const visiblePrefix = plainTextKey.substring(0, 12) + '...'
  
  // 4. Save to database using the user's RLS authority
  const { error } = await supabase.from('api_keys').insert({
    user_id: user.id,
    key_hash: hashedKey,
    key_prefix: visiblePrefix,
    name: keyName
  })
  
  if (error) {
    throw new Error(`Failed to generate key: ${error.message}`)
  }
  
  // 5. Return the raw plaintext key exactly once. 
  // We NEVER store this, so if they lose it, it's gone.
  return plainTextKey
}
