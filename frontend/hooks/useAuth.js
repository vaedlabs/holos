'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getToken, removeToken } from '@/lib/api'

/**
 * True if a login token is stored and has not expired. An expired token is removed,
 * so pages don't redirect to the dashboard only to get a 401 there.
 */
export function hasValidToken() {
  const token = getToken()
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    if (payload.exp && payload.exp * 1000 <= Date.now()) {
      removeToken()
      return false
    }
    return true
  } catch {
    removeToken() // not a readable token
    return false
  }
}

/**
 * Hook to protect routes that require authentication
 * Redirects to login if user is not authenticated
 */
export function useRequireAuth() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted) return
    
    if (!hasValidToken()) {
      router.push('/login')
      return
    }
    setIsAuthenticated(true)
  }, [mounted, router])

  return { mounted, isAuthenticated }
}

/**
 * Hook to redirect authenticated users away from auth pages (login/register)
 * Redirects to dashboard if user is already logged in
 */
export function useRedirectIfAuthenticated() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted) return
    
    if (hasValidToken()) {
      router.push('/dashboard')
    }
  }, [mounted, router])

  return { mounted }
}

