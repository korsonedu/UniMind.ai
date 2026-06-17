/** @type {import('tailwindcss').Config} */
export default {
    darkMode: ["class"],
    content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
  	extend: {
  		fontFamily: {
  			display: ['"Playfair Display"', 'serif'],
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		colors: {
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			},
  			unimind: {
  				blue: 'hsl(var(--unimind-blue))',
  				red: 'hsl(var(--unimind-red))',
  				green: 'hsl(var(--unimind-green))',
  				text: 'hsl(var(--unimind-text))',
  				'text-secondary': 'hsl(var(--unimind-text-secondary))',
  				'text-tertiary': 'hsl(var(--unimind-text-tertiary))',
  				'text-quaternary': 'hsl(var(--unimind-text-quaternary))',
  				border: 'hsl(var(--unimind-border))',
  				'bg-secondary': 'hsl(var(--unimind-bg-secondary))',
  			},
  			xiaoyu: {
  				'50': 'hsl(var(--xiaoyu-50))',
  				'100': 'hsl(var(--xiaoyu-100))',
  				'200': 'hsl(var(--xiaoyu-200))',
  				'300': 'hsl(var(--xiaoyu-300))',
  				'400': 'hsl(var(--xiaoyu-400))',
  				'500': 'hsl(var(--xiaoyu-500))',
  				'600': 'hsl(var(--xiaoyu-600))',
  			}
  		}
  	}
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
}
