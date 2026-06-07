import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  fullWidth?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({
    variant = 'primary',
    size = 'md',
    loading = false,
    fullWidth = false,
    disabled,
    className = '',
    children,
    ...props
  }, ref) => {
    const baseClasses = 'font-semibold rounded-lg transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed';

    const variants = {
      primary: 'bg-gradient-to-r from-blue-600 to-blue-700 text-white hover:shadow-lg hover:shadow-blue-500/50 active:scale-95',
      secondary: 'bg-slate-900 text-white hover:bg-slate-800 active:scale-95 shadow-md',
      outline: 'border-2 border-slate-900 text-slate-900 hover:bg-slate-50 active:bg-slate-100',
      ghost: 'text-slate-700 hover:bg-slate-100 active:bg-slate-200',
    };

    const sizes = {
      sm: 'px-3 py-2 text-sm',
      md: 'px-4 py-2.5 text-base',
      lg: 'px-6 py-3 text-lg',
    };

    const width = fullWidth ? 'w-full' : '';

    return (
      <button
        ref={ref}
        className={`${baseClasses} ${variants[variant]} ${sizes[size]} ${width} ${loading ? 'opacity-60' : ''} ${className}`}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <span className="animate-spin mr-1">⏳</span>}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
