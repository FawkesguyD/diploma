import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ObjectCard } from './ObjectCard';

const favoritesMock = vi.fn();
const addFavoriteMock = vi.fn();
const removeFavoriteMock = vi.fn();

vi.mock('@/api/hooks', () => ({
  useFavorites: favoritesMock,
  useAddFavorite: addFavoriteMock,
  useRemoveFavorite: removeFavoriteMock,
}));

const object = {
  id: 'obj-1',
  channel_site: 'Cian',
  url: 'https://example.com/object/1',
  listing: {
    title: '2-комнатная квартира',
    address: {
      city: 'Москва',
      district_slug: 'ЦАО',
    },
    price: 8500000,
    price_per_m2: 170000,
    rooms: 2,
    area: 50,
    floor: 3,
    total_floors: 7,
  },
  evaluation: {
    is_undervalued: true,
    predicted_price: 9200000,
    deviation_pct: -7.8,
  },
} as const;

describe('ObjectCard', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    favoritesMock.mockReturnValue({ data: [] });
    addFavoriteMock.mockReturnValue({ mutate: vi.fn() });
    removeFavoriteMock.mockReturnValue({ mutate: vi.fn() });
  });

  it('renders object details and toggles favorite', async () => {
    const add = vi.fn();
    addFavoriteMock.mockReturnValue({ mutate: add });

    render(<ObjectCard object={object} />);

    expect(screen.getByText('2-комнатная квартира')).toBeInTheDocument();
    expect(screen.getByText('ЦАО')).toBeInTheDocument();
    expect(screen.getByText('Москва')).toBeInTheDocument();
    expect(screen.getByText(/8.*500.*000/)).toBeInTheDocument();
    expect(screen.getByText(/170.*000/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Открыть/ })).toHaveAttribute('href', object.url);

    const button = screen.getByRole('button', { name: /В избранное/ });
    await userEvent.click(button);

    expect(add).toHaveBeenCalledWith({ target_kind: 'object', target_ref: object.id });
  });

  it('shows favorite state and removes favorite', async () => {
    const remove = vi.fn();
    favoritesMock.mockReturnValue({ data: [{ target_ref: object.id, target_kind: 'object' }] });
    removeFavoriteMock.mockReturnValue({ mutate: remove });

    render(<ObjectCard object={object} />);

    const button = screen.getByRole('button', { name: /Убрать из избранного/ });
    await userEvent.click(button);

    expect(remove).toHaveBeenCalledWith({ target_kind: 'object', target_ref: object.id });
  });
});
