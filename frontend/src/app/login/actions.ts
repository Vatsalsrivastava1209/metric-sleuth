'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'

export async function login(formData: FormData) {
  const supabase = await createClient()

  const { error } = await supabase.auth.signInWithPassword({
    email: formData.get('email') as string,
    password: formData.get('password') as string,
  })

  if (error) {
    const msg = error.message.toLowerCase()
    if (msg.includes('invalid') || msg.includes('credentials')) {
      redirect('/login?error=Email+or+password+is+incorrect')
    }
    if (msg.includes('confirm') || msg.includes('verified')) {
      redirect('/login?error=Please+confirm+your+email+before+signing+in')
    }
    redirect(`/login?error=${encodeURIComponent(error.message)}`)
  }

  revalidatePath('/', 'layout')
  redirect('/dashboard')
}

export async function signup(formData: FormData) {
  const supabase = await createClient()

  const email = formData.get('email') as string
  const password = formData.get('password') as string

  const { data, error } = await supabase.auth.signUp({ email, password })

  if (error) {
    const msg = error.message.toLowerCase()
    if (msg.includes('already') || msg.includes('registered')) {
      redirect('/login?error=An+account+with+this+email+already+exists.+Sign+in+instead.')
    }
    if (msg.includes('password')) {
      redirect(`/login?mode=signup&error=${encodeURIComponent(error.message)}`)
    }
    redirect(`/login?mode=signup&error=${encodeURIComponent(error.message)}`)
  }

  // Email confirmation required — no session yet
  if (!data.session) {
    redirect('/login?message=check-email')
  }

  revalidatePath('/', 'layout')
  redirect('/dashboard')
}

export async function signout() {
  const supabase = await createClient()
  await supabase.auth.signOut()
  redirect('/login')
}
