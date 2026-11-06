/** The same keys as the English texts, every value a string (NFR-10). */
export type Messages<T> = {
  [K in keyof T]: T[K] extends string ? string : Messages<T[K]>;
};
