"use client"

import Image from "next/image"

export function Header() {
  return (
    <header className="border-b border-[#2A3340] bg-[#0B0F14] py-8">
      <div className="container mx-auto max-w-4xl px-4">
        <div className="flex flex-col items-center text-center gap-3">
          <Image
            src="/images/logo.jpg"
            alt="EnergyMind"
            width={240}
            height={240}
            className="rounded-2xl object-cover"
            priority
          />
          <h1 className="text-4xl font-bold text-white tracking-tight">EnergyMind</h1>
          <p className="text-base text-[#94A3B8]">Legal RAG · Renewable Energy</p>
        </div>
      </div>
    </header>
  )
}
