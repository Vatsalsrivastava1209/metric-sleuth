'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const PLANS = [
  {
    id: 'free',
    label: 'Starter',
    price: '$0/mo',
    accent: 'slate',
    features: ['Up to 3 client workspaces', 'Manual investigations', 'Internal markdown exports', 'Single operator setup'],
  },
  {
    id: 'pro',
    label: 'Growth',
    price: '$499/mo',
    accent: 'blue',
    features: ['Up to 15 client workspaces', 'Client-ready PDF briefs', 'Pattern library access', 'Agency branding and Slack delivery'],
  },
  {
    id: 'business',
    label: 'Portfolio',
    price: '$1,500+/mo',
    accent: 'amber',
    features: ['50+ client workspaces', 'Priority automation and support', 'Scheduled monitoring and alerts', 'Enterprise onboarding for larger agency teams'],
  },
] as const

type BillingProfile = {
  subscription_tier: string
  stripe_customer_id: string
}

export function BillingWorkbench({ token, profile }: { token: string; profile: BillingProfile }) {
  const [message, setMessage] = useState(
    'Billing is handled through Stripe. Choose the plan that matches the number of client accounts your team actively monitors.'
  )
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null)

  const startCheckout = async (tier: 'pro' | 'business') => {
    setLoadingPlan(tier)
    try {
      const origin = window.location.origin
      const response = await fetch(`${API_BASE_URL}/api/v1/account/billing/checkout`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          tier,
          success_url: `${origin}/dashboard/billing?upgraded=1`,
          cancel_url: `${origin}/dashboard/billing`,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Checkout failed with status ${response.status}`)
      }
      window.location.href = payload.checkout_url as string
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not start checkout.')
      setLoadingPlan(null)
    }
  }

  const openPortal = async () => {
    setLoadingPlan('portal')
    try {
      const origin = window.location.origin
      const response = await fetch(`${API_BASE_URL}/api/v1/account/billing/portal`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ return_url: `${origin}/dashboard/billing` }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Portal failed with status ${response.status}`)
      }
      window.location.href = payload.portal_url as string
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not open the billing portal.')
      setLoadingPlan(null)
    }
  }

  return (
    <div className="space-y-6">
      <Card className="border-slate-800 bg-slate-900/60">
        <CardHeader>
          <CardTitle className="text-lg text-slate-200">Current portfolio plan</CardTitle>
          <CardDescription className="text-slate-400">
            Subscription state, client-account capacity, and self-serve billing actions.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 p-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500">Active plan</div>
              <div className="text-xl font-semibold text-white">{profile.subscription_tier.toUpperCase()}</div>
            </div>
            {profile.stripe_customer_id ? (
              <Button onClick={openPortal} className="bg-blue-600 text-white hover:bg-blue-700">
                {loadingPlan === 'portal' ? 'Opening...' : 'Manage in Stripe'}
              </Button>
            ) : null}
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-sm text-slate-300">
            {message}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        {PLANS.map((plan) => {
          const isCurrent = plan.id === profile.subscription_tier
          const accentClass =
            plan.accent === 'blue'
              ? 'border-blue-500/40'
              : plan.accent === 'amber'
                ? 'border-amber-500/40'
                : 'border-slate-700'

          return (
            <Card key={plan.id} className={`bg-slate-900/60 ${accentClass}`}>
              <CardHeader>
                <CardTitle className="text-lg text-slate-100">{plan.label}</CardTitle>
                <CardDescription className="text-slate-400">{plan.price}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2 text-sm text-slate-300">
                  {plan.features.map((feature) => (
                    <div key={feature}>- {feature}</div>
                  ))}
                </div>
                {isCurrent ? (
                  <Button disabled variant="outline" className="w-full border-slate-700 bg-slate-950 text-slate-300">
                    Current Plan
                  </Button>
                ) : plan.id === 'free' ? (
                  <Button disabled variant="outline" className="w-full border-slate-700 bg-slate-950 text-slate-500">
                    Base Tier
                  </Button>
                ) : (
                  <Button
                    onClick={() => startCheckout(plan.id)}
                    className="w-full bg-blue-600 text-white hover:bg-blue-700"
                    disabled={loadingPlan === plan.id}
                  >
                    {loadingPlan === plan.id ? 'Redirecting...' : `Upgrade to ${plan.label}`}
                  </Button>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
