from concurrent.futures import ThreadPoolExecutor
from typing import Generator, Iterable, Set
from functools import lru_cache
from time import sleep, ctime

from requests import get, RequestException

from base import MacBook, MODEL_REFURB_URL, FIND_TERMS, BASE_URL, WAIT_SECONDS,\
    THREADS, LRU_CACHE_SIZE, SEND_EMAIL, RETRY
from parse import HtmlWrapper
from send import send_macbook_msg


ProductGenerator = Generator[HtmlWrapper, None, None]
MacBookGenerator = Generator[MacBook, None, None]


def wrap_page(url: str=MODEL_REFURB_URL) -> HtmlWrapper:
    response = get(url)

    return HtmlWrapper(response.content)


def gen_products(page: HtmlWrapper) -> ProductGenerator:
    products = page.find_all('tr', 'product', gen=True)  # get a gen

    yield from products


# func will be consecutively hit twice with the same product in some cases.
# scraping is expensive, passing around the result is messy.
@lru_cache(maxsize=LRU_CACHE_SIZE)
def get_specs(product: HtmlWrapper) -> str:
    return product.find('td', 'specs').text.strip()


def is_match(specs: str, terms: Iterable[str]=FIND_TERMS) -> bool:
    return all(term in specs for term in terms)


def gen_filter_products(products: Iterable[HtmlWrapper],
                        terms: Iterable[str]=FIND_TERMS) -> ProductGenerator:
    for product in products:
        specs = get_specs(product)

        if is_match(specs, terms):
            yield product


def gen_filter_macbooks(macbooks: Iterable[MacBook],
                        terms: Iterable[str]=FIND_TERMS) -> MacBookGenerator:
    for macbook in macbooks:
        if is_match(macbook.specs, terms):
            yield macbook


def get_macbook(product: HtmlWrapper) -> MacBook:
    header = product.h3.a

    title = header.text.strip()
    link = BASE_URL + header['href']
    price = product.find('span', 'price').text.strip()
    specs = get_specs(product)

    return MacBook(title, link, price, specs)


def gen_macbooks(products: Iterable[HtmlWrapper]) -> MacBookGenerator:
    for product in products:
        yield get_macbook(product)


def gen_macbook_matches(page: HtmlWrapper,
                        terms: Iterable[str]=FIND_TERMS) -> MacBookGenerator:
    products_gen = gen_products(page)
    filter_gen = gen_filter_products(products_gen, terms)
    macbooks_gen = gen_macbooks(filter_gen)

    yield from macbooks_gen


def consume_macbooks(macbooks: Iterable[MacBook],
                     pool: ThreadPoolExecutor,
                     seen: Set[MacBook],
                     send_email: bool) -> None:

    for macbook in macbooks:
        print('Listing:', macbook, "\n")

        if macbook not in seen:
            seen.add(macbook)

            if send_email:
                pool.submit(send_macbook_msg, macbook)


def loop(seen: Set[MacBook],
         pool: ThreadPoolExecutor,
         url: str=MODEL_REFURB_URL,
         terms: Iterable[str]=FIND_TERMS,
         wait: float=WAIT_SECONDS,
         send_email: bool=SEND_EMAIL) -> None:

    while True:
        try:
            page = wrap_page(url)

        except RequestException as ex:
            sleep(RETRY)
            print("Retrying request.")

            continue

        macbooks = gen_macbook_matches(page, terms)
        consume_macbooks(macbooks, pool, seen, send_email)

        print("Seen:", len(seen), "@", ctime(), "Sleep:", wait)
        sleep(wait)


def main():
    seen = set()

    with ThreadPoolExecutor(THREADS) as pool:
        loop(seen, pool)


if __name__ == "__main__":
    main()
