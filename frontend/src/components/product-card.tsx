import { type Locale, type ProductSnapshot } from "@/lib/api";
import { formatDiscount, formatPrice } from "@/lib/utils";

interface ProductCardProps {
  product: ProductSnapshot;
  locale: Locale;
}

export function ProductCard({ product, locale }: ProductCardProps) {
  return (
    <a
      href={product.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group overflow-hidden rounded-lg border border-border bg-background transition-shadow hover:shadow-md"
    >
      {/* Image */}
      <div className="relative aspect-[3/4] overflow-hidden bg-muted">
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.name}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <svg
              className="h-10 w-10"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21z"
              />
            </svg>
          </div>
        )}

        {/* Discount badge */}
        {product.discount_pct > 0 && (
          <span className="absolute right-2 top-2 rounded-md bg-red-600 px-1.5 py-0.5 text-xs font-semibold text-white">
            {formatDiscount(product.discount_pct)}
          </span>
        )}
      </div>

      {/* Details */}
      <div className="p-2.5">
        <p className="truncate text-xs text-muted-foreground">
          {product.category}
        </p>
        <h3 className="mt-0.5 line-clamp-2 text-sm font-medium leading-tight">
          {product.name}
        </h3>
        <div className="mt-1.5 flex items-baseline gap-1.5">
          <span className="text-sm font-bold text-primary-600">
            {formatPrice(product.price, locale)}
          </span>
          {product.original_price > product.price && (
            <span className="text-xs text-muted-foreground line-through">
              {formatPrice(product.original_price, locale)}
            </span>
          )}
        </div>
        {product.available_sizes.length > 0 && (
          <p className="mt-1.5 truncate text-xs text-muted-foreground">
            {product.available_sizes.join(", ")}
          </p>
        )}
      </div>
    </a>
  );
}
