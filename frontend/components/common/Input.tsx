import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helpText?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helpText, className = '', ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-semibold text-slate-900 mb-2">
            {label}
          </label>
        )}
        <input
          ref={ref}
          className={`w-full px-4 py-2.5 border-2 rounded-lg font-normal transition-all duration-200 focus:outline-none ${
            error
              ? 'border-red-500 focus:border-red-600 focus:ring-2 focus:ring-red-100 bg-red-50'
              : 'border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 hover:border-slate-400'
          } ${className}`}
          {...props}
        />
        {error && <p className="text-red-600 text-sm font-medium mt-1.5">{error}</p>}
        {helpText && !error && <p className="text-slate-500 text-sm mt-1.5">{helpText}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';
