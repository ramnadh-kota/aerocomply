/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // /organization/roles has repeatedly hit Next's default 60s static-generation
  // budget on Vercel's shared build machines even though no infinite loop was
  // found after two rounds of code audit (see git history on this branch).
  // This is the Next-documented remedy for that specific timeout class:
  // https://nextjs.org/docs/messages/static-page-generation-timeout
  staticPageGenerationTimeout: 180,
};

export default nextConfig;
