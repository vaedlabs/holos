'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getToken } from '@/lib/api'

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
    
    const token = getToken()
    if (!token) {
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
    
    const token = getToken()
    if (token) {
      router.push('/dashboard')
    }
  }, [mounted, router])

  return { mounted }
}

